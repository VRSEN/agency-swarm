"""Process-level registry of persistent MCP server connections."""

import asyncio
import inspect
import logging
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from agency_swarm.tools.mcp_oauth_bridge import (
    _OAUTH_AVAILABLE,
    _get_oauth_runtime_context,
    _get_oauth_user_id,
    _MCPServerOAuth,
    _MCPServerOAuthClient,
    _set_oauth_runtime_context,
    _set_oauth_user_id,
    apply_managed_oauth_cache_dir,
)

if TYPE_CHECKING:
    from agency_swarm.mcp.oauth import MCPServerOAuth

logger = logging.getLogger(__name__)

_OAUTH_LIST_TOOLS_TIMEOUT_SECONDS = 620.0
_OAUTH_LIST_TOOLS_TIMEOUT_GRACE_SECONDS = 20.0


class PersistentMCPServerManager:
    """Process-level registry for MCP servers with persistent connections.
    Servers are keyed by their readable `name` attribute. New agencies/agents
    should reuse these instances instead of creating new ones to preserve a
    single connection per process.
    """

    def __init__(self) -> None:
        self._servers: dict[str, Any] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        self._bg_loop: asyncio.AbstractEventLoop | None = None
        self._bg_thread: threading.Thread | None = None
        self._sync_shutdown_lock: threading.Lock = threading.Lock()
        self._registration_lock: threading.Lock = threading.Lock()
        self._atexit_registered: bool = False
        # Default timeouts for known methods; unknown methods use a safe default
        self._timeouts: dict[str, float] = {
            "connect": 20.0,
            "list_tools": 10.0,
            "call_tool": 120.0,
            "cleanup": 10.0,
            "list_prompts": 10.0,
            "get_prompt": 10.0,
            "__aenter__": 15.0,
            "__aexit__": 15.0,
        }
        # Server -> driver mapping (driver runs on background loop in a single task)
        self._drivers: dict[Any, dict[str, Any]] = {}

    def _resolve_method_timeout(self, server: Any, method_name: str) -> float:
        """Resolve timeout for a method call, extending OAuth discovery waits only when needed."""
        timeout = self._timeouts.get(method_name, 30.0)
        if method_name != "list_tools":
            return timeout

        actual = getattr(server, "_server", server)
        if _MCPServerOAuthClient is None or not isinstance(actual, _MCPServerOAuthClient):
            return timeout

        if _get_oauth_runtime_context is None:
            return _OAUTH_LIST_TOOLS_TIMEOUT_SECONDS

        runtime_context = _get_oauth_runtime_context()
        runtime_timeout = getattr(runtime_context, "timeout", None) if runtime_context is not None else None
        if isinstance(runtime_timeout, (int, float)) and runtime_timeout > 0:
            return float(runtime_timeout) + _OAUTH_LIST_TOOLS_TIMEOUT_GRACE_SECONDS
        return _OAUTH_LIST_TOOLS_TIMEOUT_SECONDS

    def _ensure_driver(self, server: Any) -> None:
        # Create a per-server driver task with a command queue if missing
        real_server = getattr(server, "_server", server)
        if real_server in self._drivers:
            return
        loop = self._ensure_bg_loop()
        queue: asyncio.Queue = asyncio.Queue()
        # Readiness event
        ready_evt = threading.Event()
        # Unwrap proxy to operate on the real server inside the driver (same task)

        # Check if this is an OAuth client (two-phase auth)
        is_oauth_client = _MCPServerOAuthClient is not None and isinstance(real_server, _MCPServerOAuthClient)

        async def _driver():
            # Connect once in this driver task to bind cancel scope and session
            try:
                if getattr(real_server, "session", None) is None and not getattr(
                    real_server, "_discovery_session", None
                ):
                    server_name = getattr(real_server, "name", "<unnamed>")
                    if is_oauth_client:
                        # Two-phase auth: defer all connections to on-demand calls
                        logger.info(
                            f"Skipping eager discovery connect for OAuth server {server_name}; will connect on demand."
                        )
                    else:
                        # Regular server: full connection
                        logger.info(f"Connecting server {server_name}")
                        await real_server.connect()
            except Exception as conn_err:
                # Log but don't crash - allow driver to start for retry/recovery
                logger.error(f"Connection failed for {getattr(real_server, 'name', '<unnamed>')}: {conn_err}")
            finally:
                ready_evt.set()

            while True:
                cmd = await queue.get()
                if cmd is None:
                    continue
                typ = cmd.get("type")
                if typ == "call":
                    method_name = cmd["method"]
                    args = cmd.get("args", ())
                    kwargs = cmd.get("kwargs", {})
                    result_fut: Future = cmd["result_fut"]
                    if _set_oauth_user_id is not None:
                        _set_oauth_user_id(cast("str | None", cmd.get("oauth_user_id")))
                    if _set_oauth_runtime_context is not None:
                        _set_oauth_runtime_context(cmd.get("oauth_runtime_context"))
                    try:
                        method = getattr(real_server, method_name)
                        res = await method(*args, **kwargs)
                        result_fut.set_result(res)
                    except BaseException as e:  # noqa: BLE001
                        result_fut.set_exception(e)
                    finally:
                        if _set_oauth_runtime_context is not None:
                            _set_oauth_runtime_context(None)
                        if _set_oauth_user_id is not None:
                            _set_oauth_user_id(None)
                elif typ == "shutdown":
                    result_fut: Future = cmd["result_fut"]
                    try:
                        cleanup = getattr(real_server, "cleanup", None)
                        if callable(cleanup):
                            cleanup_result = cleanup()
                            if inspect.isawaitable(cleanup_result):
                                await cleanup_result
                        result_fut.set_result(True)
                    except BaseException as e:  # noqa: BLE001
                        result_fut.set_exception(e)
                    break
                elif typ == "force_stop":
                    result_fut = cmd.get("result_fut")
                    if isinstance(result_fut, Future) and not result_fut.done():
                        result_fut.set_result(False)
                    break

        # Start driver
        driver_future = asyncio.run_coroutine_threadsafe(_driver(), loop)
        # Wait until driver has connected
        if not ready_evt.wait(timeout=self._timeouts.get("connect", 20.0)):
            # Handle timeout explicitly
            raise TimeoutError(f"Server {getattr(server, 'name', '<unnamed>')} failed to connect within timeout")
        # Track whether this driver created a session (regular or discovery)
        has_session = getattr(real_server, "session", None) is not None
        has_discovery = getattr(real_server, "_discovery_session", None) is not None
        created_by_driver = has_session or has_discovery
        self._drivers[real_server] = {
            "queue": queue,
            "real": real_server,
            "created_by_driver": created_by_driver,
            "driver_future": driver_future,
        }

    async def ensure_connected(self, server: Any) -> None:
        # Ensure the per-server driver is running and connected
        async with self._lock:
            self._ensure_driver(server)

    async def reconnect(self, server: Any) -> None:
        """Force reconnection by clearing the existing driver and creating a new one.

        Args:
            server: The MCP server to reconnect (can be proxy or real server)
        """
        # Unwrap proxy to get real server
        real_server = getattr(server, "_server", server)

        async with self._lock:
            # Clear the existing driver if present
            if real_server in self._drivers:
                server_name = getattr(real_server, "name", "<unnamed>")
                logger.info(f"Clearing stale driver for {server_name}")
                driver_state = self._drivers.pop(real_server)

                # Try to cleanup the old driver gracefully
                try:
                    queue = driver_state.get("queue")
                    if queue:
                        # Send shutdown command
                        from concurrent.futures import Future

                        fut: Future = Future()
                        queue.put_nowait({"type": "shutdown", "result_fut": fut})
                        # Don't wait for it, just move on
                except Exception:
                    pass  # Ignore cleanup errors

            # Clear session to force reconnection
            if hasattr(real_server, "session"):
                real_server.session = None

            # Re-create the driver (this will reconnect)
            self._ensure_driver(real_server)

    async def connect_all(self) -> None:
        for server in self._servers.values():
            await self.ensure_connected(server)

    async def shutdown(self) -> None:
        """Cleanup all persistent servers and clear the registry."""
        async with self._lock:
            # Drive shutdown via driver queues to guarantee same-task cleanup
            for _, state in list(self._drivers.items()):
                queue: asyncio.Queue = state["queue"]
                fut: Future = Future()

                def _post(queue=queue, fut=fut):
                    queue.put_nowait({"type": "shutdown", "result_fut": fut})

                loop = self._ensure_bg_loop()
                loop.call_soon_threadsafe(_post)
                server_name = getattr(state.get("real"), "name", "<unnamed>")
                try:
                    fut.result(timeout=self._timeouts.get("cleanup", 10.0))
                except TimeoutError:
                    logger.warning(
                        "Timed out waiting for MCP server '%s' cleanup; forcing shutdown",
                        server_name,
                    )

                    def _force_stop(queue=queue, fut=fut):
                        queue.put_nowait({"type": "force_stop", "result_fut": fut})

                    loop.call_soon_threadsafe(_force_stop)
                    try:
                        fut.result(timeout=0.5)
                    except TimeoutError:
                        logger.warning(
                            "Force-stop for MCP server '%s' did not complete in time",
                            server_name,
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Error during MCP server '%s' shutdown: %s",
                        server_name,
                        exc,
                    )
            self._drivers.clear()
            self._servers.clear()
            if self._bg_loop is not None:
                try:
                    self._bg_loop.call_soon_threadsafe(self._bg_loop.stop)
                    if self._bg_thread is not None:
                        self._bg_thread.join(timeout=2)
                finally:
                    self._bg_loop = None
                    self._bg_thread = None

    async def unregister_keys_ending_with(self, suffix: str) -> None:
        """Cleanup and remove registered servers whose persistence keys end with suffix."""
        if suffix == "":
            return
        async with self._lock:
            matches = [key for key in self._servers if key.endswith(suffix)]
            for key in matches:
                server = self._servers.pop(key, None)
                if server is not None:
                    await self._shutdown_server_unlocked(server)

    def register(self, server: Any, *, key: str | None = None) -> Any:
        """Register (or reuse) a server by key and return the canonical instance."""
        name = key or getattr(server, "name", None)
        if not isinstance(name, str) or name == "":
            # Do not persist unnamed servers
            return server
        existing = self._servers.get(name)
        if existing is not None:
            return existing
        self._servers[name] = server
        return server

    def get(self, name: str) -> Any | None:
        return self._servers.get(name)

    def all(self) -> list[Any]:
        return list(self._servers.values())

    def update_oauth_cache_dir(self, cache_dir: Path | None) -> None:
        """Update cache_dir for all OAuth-enabled servers registered with this manager."""
        if not _OAUTH_AVAILABLE:
            return
        normalized = None
        if cache_dir is not None:
            normalized = cache_dir.expanduser()
        for server in self._servers.values():
            self._apply_cache_dir_to_server(server, normalized)
        # Update drivers as well (LoopAffineAsyncProxy->real server)
        for entry in self._drivers.values():
            real_server = entry.get("real")
            if real_server is not None:
                self._apply_cache_dir_to_server(real_server, normalized)

    def _apply_cache_dir_to_server(self, server: Any, cache_dir: Path | None) -> None:
        """Internal helper to apply cache_dir to both configs and instantiated clients."""
        if server is None:
            return
        actual = getattr(server, "_server", server)
        if _MCPServerOAuth is not None and isinstance(actual, _MCPServerOAuth):
            oauth_config = cast("MCPServerOAuth", actual)
            apply_managed_oauth_cache_dir(oauth_config, cache_dir)
            return
        try:
            from agency_swarm.mcp.oauth_client import MCPServerOAuthClient
        except ImportError:  # pragma: no cover - optional dependency missing
            return

        if isinstance(actual, MCPServerOAuthClient):
            config = actual.oauth_config
            apply_managed_oauth_cache_dir(config, cache_dir)
            oauth_provider = getattr(actual, "_oauth_provider", None)
            storage = getattr(oauth_provider, "storage", None) if oauth_provider else None
            if storage and hasattr(storage, "base_cache_dir") and cache_dir is not None:
                storage.base_cache_dir = cache_dir

    async def _shutdown_server_unlocked(self, server: Any) -> None:
        real_server = getattr(server, "_server", server)
        state = self._drivers.pop(real_server, None)
        if state is not None:
            queue: asyncio.Queue = state["queue"]
            fut: Future = Future()
            loop = self._ensure_bg_loop()
            loop.call_soon_threadsafe(lambda: queue.put_nowait({"type": "shutdown", "result_fut": fut}))
            running_loop = asyncio.get_running_loop()
            try:
                await running_loop.run_in_executor(None, fut.result, self._timeouts.get("cleanup", 10.0))
            except TimeoutError:
                driver_future = state.get("driver_future")
                if isinstance(driver_future, Future):
                    driver_future.cancel()
            return

        cleanup = getattr(real_server, "cleanup", None)
        if callable(cleanup):
            cleanup_result = cleanup()
            if inspect.isawaitable(cleanup_result):
                await cleanup_result

    def _ensure_bg_loop(self) -> asyncio.AbstractEventLoop:
        if self._bg_loop is not None:
            return self._bg_loop
        loop = asyncio.new_event_loop()

        def _runner() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(target=_runner, name="mcp-persistence-loop", daemon=True)
        thread.start()
        self._bg_loop = loop
        self._bg_thread = thread
        return loop

    def _submit_to_loop(self, coro: Any) -> Future:
        loop = self._ensure_bg_loop()
        return asyncio.run_coroutine_threadsafe(coro, loop)

    def _submit_driver_call(self, server: Any, method: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Future:
        """Schedule a coroutine method call on the server's long-lived driver task."""
        real_server = getattr(server, "_server", server)
        self._ensure_driver(real_server)
        state = self._drivers.get(real_server)
        if state is None:
            raise RuntimeError(f"Driver not initialized for server {getattr(real_server, 'name', '<unnamed>')}")

        queue: asyncio.Queue = state["queue"]
        fut: Future = Future()

        def _post_call() -> None:
            oauth_user_id = _get_oauth_user_id() if _get_oauth_user_id is not None else None
            oauth_runtime_context = _get_oauth_runtime_context() if _get_oauth_runtime_context is not None else None
            queue.put_nowait(
                {
                    "type": "call",
                    "method": method,
                    "args": args,
                    "kwargs": kwargs,
                    "oauth_user_id": oauth_user_id,
                    "oauth_runtime_context": oauth_runtime_context,
                    "result_fut": fut,
                }
            )

        loop = self._ensure_bg_loop()
        loop.call_soon_threadsafe(_post_call)
        return fut

    async def _await_future(self, fut: Future, timeout: float | None = None) -> Any:  # noqa: ANN401
        loop = asyncio.get_running_loop()

        def _get_result():
            return fut.result(timeout=timeout)

        return await loop.run_in_executor(None, _get_result)

    def mark_atexit_registered(self) -> bool:
        with self._registration_lock:
            if self._atexit_registered:
                return False
            self._atexit_registered = True
            return True

    def shutdown_sync(self) -> None:
        if not self._sync_shutdown_lock.acquire(blocking=False):
            return
        try:
            try:
                asyncio.run(self.shutdown())
            except RuntimeError as exc:
                message = str(exc)
                if "asyncio.run() cannot be called from a running event loop" not in message:
                    logger.warning("Error during persistent MCP manager shutdown: %s", exc)
                    return
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError as loop_error:
                    logger.warning(
                        "Error during persistent MCP manager shutdown: %s",
                        loop_error,
                    )
                    return
                loop.create_task(self.shutdown())
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error during persistent MCP manager shutdown: %s", exc)
        finally:
            self._sync_shutdown_lock.release()

"""Process-level registry of persistent MCP server connections.

The Agents SDK owns the connect/cleanup lifecycle: every registered server is bound to a
dedicated :class:`agents.mcp.MCPServerManager` running ``connect_in_parallel=True``, so an
SDK worker task owns each server's ``connect``/``cleanup`` pair with in-task timeouts on the
background loop (the AnyIO cancel-scope affinity MCP transports require).

What stays custom is what the SDK does not cover: the persistence registry and its keys, the
background-loop bridging used by :class:`LoopAffineAsyncProxy`, per-call OAuth context
propagation into the worker task, OAuth on-demand connection, and OAuth-aware timeouts.
"""

import asyncio
import inspect
import logging
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import Any

from agents.mcp import MCPServerManager

from agency_swarm.tools.mcp_oauth_bridge import (
    _OAUTH_AVAILABLE,
    _get_oauth_runtime_context,
    _get_oauth_user_id,
    _MCPServerOAuthClient,
    apply_oauth_cache_dir,
)
from agency_swarm.tools.mcp_server_binding import _BoundMCPServer, _ServerBinding

logger = logging.getLogger(__name__)

_OAUTH_LIST_TOOLS_TIMEOUT_SECONDS = 620.0
_OAUTH_LIST_TOOLS_TIMEOUT_GRACE_SECONDS = 20.0
# Extra caller-side wait so the SDK's in-task lifecycle timeout fires first.
_LIFECYCLE_AWAIT_GRACE_SECONDS = 5.0


class PersistentMCPServerManager:
    """Process-level registry for MCP servers with persistent connections.

    Servers are keyed by their readable `name` attribute (or OAuth persistence key).
    New agencies/agents should reuse these instances instead of creating new ones to
    preserve a single connection per process. Connect/cleanup/reconnect are delegated to
    a per-server ``agents.mcp.MCPServerManager`` driven on a shared background loop.
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
        # real server -> SDK lifecycle binding
        self._bindings: dict[Any, _ServerBinding] = {}

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

    @staticmethod
    def _is_oauth_client(server: Any) -> bool:
        return _MCPServerOAuthClient is not None and isinstance(server, _MCPServerOAuthClient)

    def _connect_timeout_for(self, real_server: Any) -> float | None:
        """Connect timeout for the SDK worker; OAuth consent must not be capped."""
        if self._is_oauth_client(real_server):
            # Interactive OAuth consent can take far longer than the standard connect
            # timeout. The caller-side method timeout bounds the wait instead, matching
            # the previous driver which never timed out a connect in-task.
            return None
        return self._timeouts.get("connect", 20.0)

    def _ensure_binding(self, server: Any) -> _ServerBinding:
        """Create the per-server SDK manager binding if missing (no connection yet)."""
        real_server = getattr(server, "_server", server)
        if real_server in self._bindings:
            return self._bindings[real_server]
        bound = _BoundMCPServer(real_server)
        sdk_manager = MCPServerManager(
            [bound],
            connect_timeout_seconds=self._connect_timeout_for(real_server),
            cleanup_timeout_seconds=self._timeouts.get("cleanup", 10.0),
            drop_failed_servers=False,
            strict=False,
            connect_in_parallel=True,
        )
        state = _ServerBinding(manager=sdk_manager, bound=bound, real=real_server)
        self._bindings[real_server] = state
        return state

    def _sync_lifecycle_timeouts(self, sdk_manager: MCPServerManager, real_server: Any) -> None:
        sdk_manager.connect_timeout_seconds = self._connect_timeout_for(real_server)
        sdk_manager.cleanup_timeout_seconds = self._timeouts.get("cleanup", 10.0)

    def _submit_connect(self, state: _ServerBinding, *, propagate_errors: bool = False) -> Future:
        """Schedule ``connect_all`` on the background loop.

        Only ``TimeoutError`` propagates by default (matching the previous ready-event
        wait); ``propagate_errors`` also re-raises recorded failures, matching a direct
        ``server.connect()`` call.
        """
        sdk_manager = state.manager
        bound = state.bound
        bound.bind_oauth_context(*self._current_oauth_context())
        self._sync_lifecycle_timeouts(sdk_manager, state.real)

        async def _connect() -> None:
            await sdk_manager.connect_all()
            error = sdk_manager.errors.get(bound)
            if error is not None and (propagate_errors or isinstance(error, TimeoutError)):
                raise error

        return self._submit_to_loop(_connect())

    def _submit_cleanup(self, state: _ServerBinding) -> Future:
        """Schedule ``cleanup_all`` on the background loop, re-raising recorded failures."""
        sdk_manager = state.manager
        bound = state.bound
        bound.bind_oauth_context(*self._current_oauth_context())
        self._sync_lifecycle_timeouts(sdk_manager, state.real)

        async def _cleanup() -> None:
            # ``MCPServerManager._errors`` is only reset on connect/reconnect, so only an
            # error recorded by *this* cleanup may propagate — a stale connect failure
            # must not be re-raised (or misreported) as a cleanup failure.
            stale_error = sdk_manager.errors.get(bound)
            await sdk_manager.cleanup_all()
            error = sdk_manager.errors.get(bound)
            if error is not None and error is not stale_error:
                raise error
            if not bound.cleanup_completed:
                # The SDK skips cleanup when no worker ever ran (e.g. a server the
                # caller connected before registering). Run it here so the session is
                # released and any pending ``__aexit__`` is still consumed.
                await bound.cleanup()

        return self._submit_to_loop(_cleanup())

    async def _await_cleanup(self, state: _ServerBinding, server_name: str) -> None:
        try:
            await self._await_future(
                self._submit_cleanup(state),
                timeout=self._timeouts.get("cleanup", 10.0) + _LIFECYCLE_AWAIT_GRACE_SECONDS,
            )
        except TimeoutError:
            logger.warning("Timed out waiting for MCP server '%s' cleanup; forcing shutdown", server_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error during MCP server '%s' shutdown: %s", server_name, exc)

    def _has_live_session(self, real_server: Any) -> bool:
        return getattr(real_server, "session", None) is not None or bool(
            getattr(real_server, "_discovery_session", None)
        )

    def _ensure_driver(self, server: Any) -> None:
        """Ensure the per-server worker exists and non-OAuth servers are connected.

        Synchronous facade used from agent init and tool conversion; blocks the caller
        thread until connect finishes, like the previous ready-event wait.
        """
        real_server = getattr(server, "_server", server)
        state = self._ensure_binding(real_server)
        if self._is_oauth_client(real_server):
            # Two-phase auth: defer all connections to on-demand calls.
            return
        if self._has_live_session(real_server):
            # The caller already connected this server; connecting again would spawn a
            # second transport on the same session. The binding still routes calls and
            # cleanup.
            return
        fut = self._submit_connect(state)
        fut.result(timeout=self._timeouts.get("connect", 20.0) + _LIFECYCLE_AWAIT_GRACE_SECONDS)

    async def ensure_connected(self, server: Any) -> None:
        """Ensure the per-server worker exists and non-OAuth servers are connected."""
        real_server = getattr(server, "_server", server)
        async with self._lock:
            state = self._ensure_binding(real_server)
            if self._is_oauth_client(real_server):
                logger.info(
                    f"Skipping eager discovery connect for OAuth server "
                    f"{getattr(real_server, 'name', '<unnamed>')}; will connect on demand."
                )
                return
            if self._has_live_session(real_server):
                return
            fut = self._submit_connect(state)
            await self._await_future(fut, timeout=self._timeouts.get("connect", 20.0) + _LIFECYCLE_AWAIT_GRACE_SECONDS)

    async def reconnect(self, server: Any) -> None:
        """Force reconnection by replacing the server binding.

        Non-OAuth servers reconnect eagerly; OAuth clients stay lazy and reconnect on the
        next call, matching the previous driver behavior.
        """
        real_server = getattr(server, "_server", server)
        server_name = getattr(real_server, "name", "<unnamed>")

        async with self._lock:
            state = self._bindings.pop(real_server, None)
            if state is not None:
                logger.info(f"Clearing stale binding for {server_name}")
                await self._await_cleanup(state, server_name)

            # Clear the session marker so a failed cleanup cannot leave a stale session
            # that suppresses the fresh connect below.
            if hasattr(real_server, "session"):
                real_server.session = None

            state = self._ensure_binding(real_server)
            if not self._is_oauth_client(real_server):
                fut = self._submit_connect(state)
                await self._await_future(
                    fut, timeout=self._timeouts.get("connect", 20.0) + _LIFECYCLE_AWAIT_GRACE_SECONDS
                )

    async def shutdown(self) -> None:
        """Cleanup all persistent servers and clear the registry."""
        async with self._lock:
            for state in list(self._bindings.values()):
                await self._await_cleanup(state, getattr(state.real, "name", "<unnamed>"))
            self._bindings.clear()
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
        servers = list(self._servers.values())
        # Bound servers as well (LoopAffineAsyncProxy->real server)
        servers.extend(binding.real for binding in self._bindings.values())
        apply_oauth_cache_dir(servers, cache_dir)

    async def _shutdown_server_unlocked(self, server: Any) -> None:
        real_server = getattr(server, "_server", server)
        state = self._bindings.pop(real_server, None)
        if state is not None:
            await self._await_cleanup(state, getattr(real_server, "name", "<unnamed>"))
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

    @staticmethod
    def _current_oauth_context() -> tuple[str | None, Any | None]:
        user = _get_oauth_user_id() if _get_oauth_user_id is not None else None
        context = _get_oauth_runtime_context() if _get_oauth_runtime_context is not None else None
        return user, context

    def _submit_call(self, server: Any, method: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Future:
        """Schedule a coroutine method call on the server's background loop."""
        real_server = getattr(server, "_server", server)
        state = self._ensure_binding(real_server)
        sdk_manager = state.manager
        bound = state.bound
        oauth_user_id, oauth_runtime_context = self._current_oauth_context()

        if method == "connect":
            return self._submit_connect(state, propagate_errors=True)
        if method == "cleanup":
            return self._submit_cleanup(state)

        async def _invoke() -> Any:  # noqa: ANN401
            if self._is_oauth_client(real_server) and getattr(real_server, "session", None) is None:
                # OAuth clients connect on demand. ``_run_connect`` drives this server's
                # worker directly: ``connect_all`` would skip a server the SDK already
                # considers connected even when its session was reset. The session is
                # created in the worker task so its cancel scopes stay affine with the
                # worker-side cleanup. OAuth connects carry no in-task timeout (consent
                # is human-slow); the caller-side method timeout bounds the wait. Errors
                # propagate — running the method after a failed connect would trigger a
                # second provider and consent prompt.
                bound.bind_oauth_context(oauth_user_id, oauth_runtime_context)
                self._sync_lifecycle_timeouts(sdk_manager, real_server)
                await sdk_manager._run_connect(bound)
            bound._set_oauth_context(oauth_user_id, oauth_runtime_context)
            try:
                method_fn = getattr(real_server, method)
                return await method_fn(*args, **kwargs)
            finally:
                bound._clear_oauth_context()

        return self._submit_to_loop(_invoke())

    def _submit_enter(self, server: Any) -> Future:
        """Run the real ``__aenter__`` inside the SDK worker task; resolves to its result."""
        return self._submit_context(server, None)

    def _submit_exit(self, server: Any, args: tuple[Any, Any, Any]) -> Future:
        """Run the real ``__aexit__`` inside the SDK worker task; resolves to its result."""
        return self._submit_context(server, args)

    def _submit_context(self, server: Any, exit_args: tuple[Any, Any, Any] | None) -> Future:
        state = self._ensure_binding(getattr(server, "_server", server))
        sdk_manager = state.manager
        bound = state.bound
        if exit_args is not None:
            bound.request_exit(exit_args)
            inner = self._submit_cleanup(state)

            async def _run() -> Any:  # noqa: ANN401
                await asyncio.wrap_future(inner)
                return bound.exit_result
        else:
            bound.bind_oauth_context(*self._current_oauth_context())
            bound.request_enter()
            self._sync_lifecycle_timeouts(sdk_manager, state.real)

            async def _run() -> Any:  # noqa: ANN401
                # ``_run_connect`` drives this server's worker task directly so the real
                # ``__aenter__`` runs there (cancel-scope affinity) *without* the
                # cleanup+reconnect that ``reconnect()`` would force — entering a context
                # must never tear down a live persistent connection first.
                await sdk_manager._run_connect(bound)
                return bound.enter_result

        return self._submit_to_loop(_run())

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
                if "asyncio.run() cannot be called from a running event loop" not in str(exc):
                    logger.warning("Error during persistent MCP manager shutdown: %s", exc)
                    return
                try:
                    asyncio.get_running_loop().create_task(self.shutdown())
                except RuntimeError as loop_error:
                    logger.warning("Error during persistent MCP manager shutdown: %s", loop_error)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error during persistent MCP manager shutdown: %s", exc)
        finally:
            self._sync_shutdown_lock.release()

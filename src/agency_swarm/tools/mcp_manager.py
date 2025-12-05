import asyncio
import inspect
import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent
    from agency_swarm.mcp.oauth import MCPServerOAuth

logger = logging.getLogger(__name__)

# OAuth support - imported conditionally to avoid circular imports
_OAUTH_AVAILABLE = False
_MCPServerOAuth: type | None = None
_MCPServerOAuthClient: type | None = None
_create_oauth_provider: Callable[..., Any] | None = None

try:
    from agency_swarm.mcp.oauth import (
        MCPServerOAuth as _MCPServerOAuth_impl,
        create_oauth_provider as _create_oauth_provider_impl,
    )
    from agency_swarm.mcp.oauth_client import MCPServerOAuthClient as _MCPServerOAuthClient_impl

    _MCPServerOAuth = _MCPServerOAuth_impl
    _MCPServerOAuthClient = _MCPServerOAuthClient_impl
    _create_oauth_provider = _create_oauth_provider_impl
    _OAUTH_AVAILABLE = True
except ImportError:
    logger.debug("OAuth support not available - install MCP SDK to enable")


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
                    try:
                        method = getattr(real_server, method_name)
                        res = await method(*args, **kwargs)
                        result_fut.set_result(res)
                    except Exception as e:  # noqa: BLE001
                        result_fut.set_exception(e)
                elif typ == "shutdown":
                    result_fut: Future = cmd["result_fut"]
                    try:
                        await real_server.cleanup()
                        result_fut.set_result(True)
                    except Exception as e:  # noqa: BLE001
                        result_fut.set_exception(e)
                    break
                elif typ == "force_stop":
                    result_fut = cmd.get("result_fut")
                    if isinstance(result_fut, Future) and not result_fut.done():
                        result_fut.set_result(False)
                    break

        # Start driver
        asyncio.run_coroutine_threadsafe(_driver(), loop)
        # Wait until driver has connected
        if not ready_evt.wait(timeout=self._timeouts.get("connect", 20.0)):
            # Handle timeout explicitly
            raise TimeoutError(f"Server {getattr(server, 'name', '<unnamed>')} failed to connect within timeout")
        # Track whether this driver created a session (regular or discovery)
        has_session = getattr(real_server, "session", None) is not None
        has_discovery = getattr(real_server, "_discovery_session", None) is not None
        created_by_driver = has_session or has_discovery
        self._drivers[real_server] = {"queue": queue, "real": real_server, "created_by_driver": created_by_driver}

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

    def register(self, server: Any) -> Any:
        """Register (or reuse) a server by name and return the canonical instance."""
        name = getattr(server, "name", None)
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
            if cache_dir is not None and getattr(oauth_config, "cache_dir", None) is None:
                oauth_config.cache_dir = cache_dir
            return
        try:
            from agency_swarm.mcp.oauth_client import MCPServerOAuthClient
        except ImportError:  # pragma: no cover - optional dependency missing
            return

        if isinstance(actual, MCPServerOAuthClient):
            config = actual.oauth_config
            if cache_dir is not None and getattr(config, "cache_dir", None) is None:
                config.cache_dir = cache_dir
            oauth_provider = getattr(actual, "_oauth_provider", None)
            storage = getattr(oauth_provider, "storage", None) if oauth_provider else None
            if storage and hasattr(storage, "base_cache_dir") and cache_dir is not None:
                storage.base_cache_dir = cache_dir

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


class LoopAffineAsyncProxy:
    """Generic proxy routing coroutine methods to the manager's background loop.

    Avoids coupling to the concrete server implementation by dynamically proxying
    any coroutine attribute via __getattr__.
    """

    def __init__(self, server: Any, manager: PersistentMCPServerManager) -> None:
        self._server = server
        self._manager = manager

    async def __aenter__(self) -> Any:  # noqa: ANN401
        target = getattr(self._server, "__aenter__", None)
        if target is None:
            raise TypeError(f"Server {self._server!r} does not support asynchronous context management")
        result = target()
        if inspect.isawaitable(result):
            fut = self._manager._submit_to_loop(result)
            timeout = self._manager._timeouts.get("__aenter__", 30.0)
            return await self._manager._await_future(fut, timeout=timeout)
        return result

    async def __aexit__(self, exc_type, exc, tb) -> Any:  # noqa: ANN001, ANN401
        target = getattr(self._server, "__aexit__", None)
        if target is None:
            raise TypeError(f"Server {self._server!r} does not support asynchronous context management")
        result = target(exc_type, exc, tb)
        if inspect.isawaitable(result):
            fut = self._manager._submit_to_loop(result)
            timeout = self._manager._timeouts.get("__aexit__", 30.0)
            return await self._manager._await_future(fut, timeout=timeout)
        return result

    def __getattr__(self, name: str):  # noqa: ANN001
        target = getattr(self._server, name)

        if inspect.iscoroutinefunction(target):
            timeout = self._manager._timeouts.get(name, 30.0)

            async def _proxy(*args, **kwargs):  # noqa: ANN001
                fut = self._manager._submit_to_loop(target(*args, **kwargs))
                return await self._manager._await_future(fut, timeout=timeout)

            return _proxy

        return target


default_mcp_manager = PersistentMCPServerManager()


def _process_oauth_servers(agent: Any, servers: list[Any]) -> None:
    """Process OAuth-enabled MCP servers and convert them to authenticated clients.

    Args:
        agent: The agent instance
        servers: List of MCP server instances (may include MCPServerOAuth)
    """
    if not _OAUTH_AVAILABLE or _MCPServerOAuth is None:
        return

    # Import OAuth client here to avoid circular import
    from agency_swarm.mcp.oauth_client import MCPServerOAuthClient

    # Get custom handlers from agent if provided
    redirect_handler = getattr(agent, "mcp_oauth_redirect_handler", None)
    callback_handler = getattr(agent, "mcp_oauth_callback_handler", None)
    handler_factory = getattr(agent, "mcp_oauth_handler_factory", None)
    base_handlers = {}
    if redirect_handler:
        base_handlers["redirect"] = redirect_handler
    if callback_handler:
        base_handlers["callback"] = callback_handler

    # Convert OAuth configs to OAuth clients
    for i, srv in enumerate(list(servers)):
        if not isinstance(srv, _MCPServerOAuth):
            continue

        # Cast to help mypy understand the type after isinstance check
        oauth_srv = cast("MCPServerOAuth", srv)

        logger.info(f"Creating OAuth client for MCP server: {oauth_srv.name}")

        try:
            # Validate configuration
            client_id = oauth_srv.get_client_id_optional()
            if client_id:
                logger.info(f"OAuth configured for {oauth_srv.name} (client_id: {client_id[:8]}...)")

            # Create OAuth client wrapper
            server_handlers = base_handlers.copy() if base_handlers else {}
            if callable(handler_factory):
                new_handlers = handler_factory(oauth_srv.name)
                if isinstance(new_handlers, dict):
                    server_handlers.update(new_handlers)
            handlers_arg = server_handlers if server_handlers else None
            oauth_client = MCPServerOAuthClient(
                oauth_srv,
                handlers_arg,
            )

            # Replace config with actual client
            servers[i] = oauth_client
            logger.info(f"OAuth client created for {oauth_srv.name}")

        except Exception:
            logger.exception(f"Failed to create OAuth client for {oauth_srv.name}")
            raise


def _sync_oauth_client_handlers(persistent: Any, candidate: Any) -> None:
    """Update cached OAuth client with per-request handlers from a new instance."""
    if not _OAUTH_AVAILABLE or _MCPServerOAuthClient is None:
        return

    existing_client = getattr(persistent, "_server", persistent)
    new_client = getattr(candidate, "_server", candidate)

    if not isinstance(existing_client, _MCPServerOAuthClient) or not isinstance(new_client, _MCPServerOAuthClient):
        return

    existing_client._redirect_handler = getattr(new_client, "_redirect_handler", None)
    existing_client._callback_handler = getattr(new_client, "_callback_handler", None)
    # Ensure next OAuth provider uses the latest handlers
    if hasattr(existing_client, "_oauth_provider"):
        existing_client._oauth_provider = None


async def attach_persistent_mcp_servers(agency: Any) -> None:
    """Attach and connect persistent MCP servers to all agents in an agency.

    - Replaces each agent's server with a shared instance keyed by `server.name`.
    - Connects servers once (if not already connected).
    - No-ops for servers without a `name` attribute.
    """
    agents_map = getattr(agency, "agents", None)
    if not isinstance(agents_map, dict):
        return
    for agent in agents_map.values():
        servers = getattr(agent, "mcp_servers", None)
        if not isinstance(servers, list):
            continue
        if _OAUTH_AVAILABLE:
            _process_oauth_servers(agent, servers)
        for i, srv in enumerate(list(servers)):
            name = getattr(srv, "name", None)
            if not isinstance(name, str) or name == "":
                raise ValueError(f"Server {srv} has no name provided")

            persistent = default_mcp_manager.get(name)
            if persistent is None:
                persistent = default_mcp_manager.register(srv)
            else:
                _sync_oauth_client_handlers(persistent, srv)
            # Replace the reference so future runs reuse the same object and ensure loop‑affine proxy
            replacement = (
                persistent
                if isinstance(persistent, LoopAffineAsyncProxy)
                else LoopAffineAsyncProxy(persistent, default_mcp_manager)
            )
            if replacement is not servers[i]:
                servers[i] = replacement
        # After replacing, ensure all are connected once
        for srv in servers:
            await default_mcp_manager.ensure_connected(srv)


def register_and_connect_agent_servers(agent: Any) -> None:
    """Register an agent's MCP servers in the persistent manager and connect them.

    This is a synchronous facade that safely handles both sync and async contexts:
    - If an event loop is running, schedules an async task to connect servers.
    - Otherwise, creates a temporary loop to connect synchronously.
    - Supports OAuth-enabled servers via MCPServerOAuth instances.
    """
    servers = getattr(agent, "mcp_servers", None)
    if not isinstance(servers, list) or len(servers) == 0:
        return

    # Process OAuth servers first
    if _OAUTH_AVAILABLE:
        _process_oauth_servers(agent, servers)

    server_names = []
    # Replace each server with the persistent instance (by name) if available
    for i, srv in enumerate(list(servers)):
        name = getattr(srv, "name", None)
        if isinstance(name, str) and name != "" and name not in server_names:
            server_names.append(name)
            persistent = default_mcp_manager.get(name) or default_mcp_manager.register(srv)
            if persistent is not srv:
                _sync_oauth_client_handlers(persistent, srv)
            if persistent is not servers[i]:
                servers[i] = persistent
        elif name in server_names:
            raise ValueError(
                f"Server {srv} has duplicate name: {name}. "
                "Please provide server with unique names by explicitly specifying the name attribute."
            )
        else:
            raise ValueError(f"Server {srv} has no name provided")

    # Establish connections during Agent init and bind all ops to background loop
    for idx, srv in enumerate(list(servers)):
        # Always use loop‑affine proxy for MCP servers
        if not isinstance(srv, LoopAffineAsyncProxy):
            proxy = LoopAffineAsyncProxy(srv, default_mcp_manager)
            servers[idx] = proxy
            srv = proxy

        # Ensure driver is created and connected on the background loop (synchronous)
        default_mcp_manager._ensure_driver(getattr(srv, "_server", srv))


def convert_mcp_servers_to_tools(agent: "Agent") -> None:
    """Convert agent's MCP servers to FunctionTool instances and add them to the agent's tools.

    This function:
    1. Converts all MCP servers to FunctionTool instances using ToolFactory.from_mcp
    2. Adds the converted tools to the agent's tools list
    3. Clears the agent's mcp_servers list

    Args:
        agent: The agent instance to process
    """
    from agency_swarm.tools.tool_factory import ToolFactory

    servers = getattr(agent, "mcp_servers", None)
    if not isinstance(servers, list) or len(servers) == 0:
        return

    if _OAUTH_AVAILABLE:
        _process_oauth_servers(agent, servers)

    # Read convert_schemas_to_strict from agent's mcp_config
    mcp_config = getattr(agent, "mcp_config", None) or {}
    convert_to_strict = mcp_config.get("convert_schemas_to_strict", False)

    # Convert MCP servers to FunctionTool instances
    converted_tools = ToolFactory.from_mcp(
        servers,
        convert_schemas_to_strict=convert_to_strict,
        context=None,
        agent=agent,
    )
    for tool in converted_tools:
        agent.add_tool(tool)

    # Clear the mcp_servers list
    agent.mcp_servers.clear()

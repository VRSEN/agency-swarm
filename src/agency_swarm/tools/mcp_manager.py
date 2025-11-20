import asyncio
import inspect
import logging
import threading
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent

logger = logging.getLogger(__name__)


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

        async def _driver():
            # Connect once in this driver task to bind cancel scope and session
            try:
                if getattr(real_server, "session", None) is None:
                    logger.info(f"Connecting server {getattr(real_server, 'name', '<unnamed>')}")
                    await real_server.connect()
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
        # Track whether this driver created the session to decide who cleans up
        created_by_driver = getattr(real_server, "session", None) is not None
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
        for i, srv in enumerate(list(servers)):
            name = getattr(srv, "name", None)
            if not isinstance(name, str) or name == "":
                raise ValueError(f"Server {srv} has no name provided")

            persistent = default_mcp_manager.get(name)
            if persistent is None:
                persistent = default_mcp_manager.register(srv)
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
    """
    servers = getattr(agent, "mcp_servers", None)
    if not isinstance(servers, list) or len(servers) == 0:
        return

    server_names = []
    # Replace each server with the persistent instance (by name) if available
    for i, srv in enumerate(list(servers)):
        name = getattr(srv, "name", None)
        if isinstance(name, str) and name != "" and name not in server_names:
            server_names.append(name)
            persistent = default_mcp_manager.get(name) or default_mcp_manager.register(srv)
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

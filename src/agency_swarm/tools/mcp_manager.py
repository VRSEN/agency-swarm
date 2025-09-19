import asyncio
import inspect
import logging
import threading
from concurrent.futures import Future
from typing import Any

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
        # Default timeouts for known methods; unknown methods use a safe default
        self._timeouts: dict[str, float] = {
            "connect": 20.0,
            "list_tools": 10.0,
            "call_tool": 120.0,
            "cleanup": 10.0,
            "list_prompts": 10.0,
            "get_prompt": 10.0,
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

        # Start driver
        asyncio.run_coroutine_threadsafe(_driver(), loop)
        # Wait until driver has connected
        if not ready_evt.wait(timeout=self._timeouts.get("connect", 20.0)):
            # Handle timeout explicitly
            raise TimeoutError(
                f"Server {getattr(server, 'name', '<unnamed>')} failed to connect within timeout"
            )
        # Track whether this driver created the session to decide who cleans up
        created_by_driver = getattr(real_server, "session", None) is not None
        self._drivers[real_server] = {"queue": queue, "real": real_server, "created_by_driver": created_by_driver}

    async def ensure_connected(self, server: Any) -> None:
        # Ensure the per-server driver is running and connected
        async with self._lock:
            self._ensure_driver(server)

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

                self._ensure_bg_loop().call_soon_threadsafe(_post)
                fut.result(timeout=self._timeouts.get("cleanup", 10.0))
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


class LoopAffineAsyncProxy:
    """Generic proxy routing coroutine methods to the manager's background loop.

    Avoids coupling to the concrete server implementation by dynamically proxying
    any coroutine attribute via __getattr__.
    """

    def __init__(self, server: Any, manager: PersistentMCPServerManager) -> None:
        self._server = server
        self._manager = manager

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

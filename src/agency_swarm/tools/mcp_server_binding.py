"""Adapter binding a real MCP server to an ``agents.mcp.MCPServerManager`` worker.

The SDK worker task only runs ``connect`` and ``cleanup``. :class:`_BoundMCPServer`
forwards them to the real server and replays a requested ``__aenter__``/``__aexit__``
pair inside the worker task, so ``async with proxy`` keeps its semantics and AnyIO
cancel scopes stay affine. OAuth contextvars do not cross threads and are replayed
where token storage reads them. Servers without ``cleanup`` are tolerated, matching
the previous manager.
"""

import inspect
from dataclasses import dataclass
from typing import Any

from agents.mcp import MCPServer, MCPServerManager

from agency_swarm.tools.mcp_oauth_bridge import _set_oauth_runtime_context, _set_oauth_user_id


class _BoundMCPServer(MCPServer):
    """Adapter handed to ``MCPServerManager`` in place of the real server.

    The SDK worker task only runs ``connect`` and ``cleanup``. This adapter forwards them to
    the real server and replays a requested ``__aenter__``/``__aexit__`` pair inside the
    worker task, so ``async with proxy`` keeps its semantics and AnyIO cancel scopes stay
    affine. OAuth contextvars do not cross threads and are replayed where token storage
    reads them. Servers without ``cleanup`` are tolerated, matching the previous manager.
    """

    def __init__(self, server: Any) -> None:
        super().__init__()
        self._server = server
        self._oauth_user_id: str | None = None
        self._oauth_runtime_context: Any | None = None
        self._enter_requested = False
        self._exit_requested = False
        # Set once a cleanup has run; reset by connect so a new session is cleaned again.
        self.cleanup_completed = False
        self.exit_args: tuple[Any, Any, Any] = (None, None, None)
        self.enter_result: Any = server
        self.exit_result: Any = None

    @property
    def name(self) -> str:
        return getattr(self._server, "name", "<unnamed>")

    def bind_oauth_context(self, user_id: str | None, runtime_context: Any | None) -> None:
        """Capture OAuth contextvars to replay inside the worker task."""
        self._oauth_user_id = user_id
        self._oauth_runtime_context = runtime_context

    def request_enter(self) -> None:
        self._enter_requested = True

    def request_exit(self, args: tuple[Any, Any, Any]) -> None:
        self._exit_requested = True
        self.exit_args = args

    def _set_oauth_context(self, user_id: str | None, runtime_context: Any | None) -> None:
        if _set_oauth_user_id is not None:
            _set_oauth_user_id(user_id)
        if _set_oauth_runtime_context is not None:
            _set_oauth_runtime_context(runtime_context)

    def _apply_oauth_context(self) -> None:
        self._set_oauth_context(self._oauth_user_id, self._oauth_runtime_context)

    def _clear_oauth_context(self) -> None:
        self._set_oauth_context(None, None)

    def _already_connected(self) -> bool:
        return getattr(self._server, "session", None) is not None or bool(
            getattr(self._server, "_discovery_session", None)
        )

    async def connect(self) -> None:
        """Runs inside the SDK worker task."""
        self.cleanup_completed = False
        self._apply_oauth_context()
        try:
            if self._enter_requested:
                self._enter_requested = False
                enter = getattr(self._server, "__aenter__", None) or self._server.connect
                result = enter()
                result = await result if inspect.isawaitable(result) else result
                self.enter_result = result if result is not None else self._server
            elif not self._already_connected():
                # A live session means the caller or a previous lifecycle run already
                # connected; re-connecting would spawn a second transport.
                await self._server.connect()
        finally:
            self._clear_oauth_context()

    async def cleanup(self) -> None:
        """Runs inside the SDK worker task."""
        self.cleanup_completed = True
        self._apply_oauth_context()
        try:
            if self._exit_requested:
                self._exit_requested = False
                exit_fn = getattr(self._server, "__aexit__", None)
                if exit_fn is not None:
                    result = exit_fn(*self.exit_args)
                    self.exit_result = await result if inspect.isawaitable(result) else result
                    return
            cleanup = getattr(self._server, "cleanup", None)
            if not callable(cleanup):
                return
            result = cleanup()
            self.exit_result = await result if inspect.isawaitable(result) else result
        finally:
            self._clear_oauth_context()

    # Remaining MCPServer abstract members delegate to the real server. The SDK worker
    # only invokes connect/cleanup, but a full implementation keeps the adapter honest.
    async def list_tools(self, run_context: Any = None, agent: Any = None) -> Any:  # noqa: ANN401
        return await self._server.list_tools(run_context, agent)

    async def call_tool(self, tool_name: str, arguments: Any = None, meta: Any = None) -> Any:  # noqa: ANN401
        return await self._server.call_tool(tool_name, arguments, meta)

    async def list_prompts(self) -> Any:  # noqa: ANN401
        return await self._server.list_prompts()

    async def get_prompt(self, name: str, arguments: Any = None) -> Any:  # noqa: ANN401
        return await self._server.get_prompt(name, arguments)


@dataclass
class _ServerBinding:
    """Per-server SDK lifecycle state tracked by the persistent manager."""

    manager: MCPServerManager
    bound: _BoundMCPServer
    real: Any

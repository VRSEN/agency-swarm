"""Loop-affine proxy that routes MCP server coroutines to the manager's background loop."""

import asyncio
import inspect
from typing import Any

from agency_swarm.tools.mcp_persistence import PersistentMCPServerManager


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
        timeout = self._manager._timeouts.get("__aenter__", 30.0)
        if inspect.iscoroutinefunction(target):
            fut = self._manager._submit_driver_call(self._server, "__aenter__", (), {})
            return await self._manager._await_future(fut, timeout=timeout)
        result = target()
        if inspect.isawaitable(result):
            fut = self._manager._submit_to_loop(result)
            return await self._manager._await_future(fut, timeout=timeout)
        return result

    async def __aexit__(self, exc_type, exc, tb) -> Any:  # noqa: ANN001, ANN401
        target = getattr(self._server, "__aexit__", None)
        if target is None:
            raise TypeError(f"Server {self._server!r} does not support asynchronous context management")
        timeout = self._manager._timeouts.get("__aexit__", 30.0)
        if inspect.iscoroutinefunction(target):
            fut = self._manager._submit_driver_call(self._server, "__aexit__", (exc_type, exc, tb), {})
            return await self._manager._await_future(fut, timeout=timeout)
        result = target(exc_type, exc, tb)
        if inspect.isawaitable(result):
            fut = self._manager._submit_to_loop(result)
            return await self._manager._await_future(fut, timeout=timeout)
        return result

    def __getattr__(self, name: str):  # noqa: ANN001
        target = getattr(self._server, name)

        if inspect.iscoroutinefunction(target):

            async def _proxy(*args, **kwargs):  # noqa: ANN001
                timeout = self._manager._resolve_method_timeout(self._server, name)
                fut = self._manager._submit_driver_call(self._server, name, args, kwargs)
                server_name = getattr(self._server, "name", "<unnamed>")
                try:
                    return await self._manager._await_future(fut, timeout=timeout)
                except TimeoutError as exc:
                    raise TimeoutError(
                        f"MCP call '{name}' timed out after {timeout:.1f}s on server '{server_name}'"
                    ) from exc
                except asyncio.CancelledError as exc:
                    current_task = asyncio.current_task()
                    if current_task is not None and current_task.cancelling():
                        raise
                    raise RuntimeError(
                        f"MCP call '{name}' was cancelled on server '{server_name}'. "
                        "Check MCP server availability and OAuth configuration."
                    ) from exc

            return _proxy

        return target

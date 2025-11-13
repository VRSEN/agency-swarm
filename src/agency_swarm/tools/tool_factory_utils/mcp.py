from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from agents import Agent as SDKAgent, FunctionTool, set_tracing_disabled
from agents.mcp.server import MCPServer
from agents.mcp.util import MCPUtil
from agents.run_context import RunContextWrapper

from agency_swarm.tools.mcp_manager import LoopAffineAsyncProxy, default_mcp_manager

if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent as AgencyAgent

logger = logging.getLogger(__name__)


def _run_coroutine_from_factory(factory: Callable[[], Awaitable[Any]]) -> Any:
    """Execute an async coroutine factory from synchronous code."""
    result: dict[str, Any] = {}
    error: list[BaseException] = []

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(factory())
        except BaseException as exc:  # noqa: BLE001
            error.append(exc)

    thread = threading.Thread(target=_runner, name="tool-factory-mcp-call", daemon=True)
    thread.start()
    thread.join()

    if error:
        raise error[0]
    if "value" not in result:
        raise RuntimeError("Coroutine execution did not produce a result")
    return result["value"]


def from_mcp(
    mcp_servers: list[MCPServer],
    *,
    convert_schemas_to_strict: bool = False,
    context: RunContextWrapper[Any] | None = None,
    agent: AgencyAgent | SDKAgent | None = None,
) -> list[FunctionTool]:
    """Convert MCP servers into standalone FunctionTool instances."""
    if not mcp_servers:
        return []

    servers = list(mcp_servers)
    run_context = context or RunContextWrapper(context=None)
    agent_for_fetch = agent if isinstance(agent, SDKAgent) else SDKAgent(name="mcp_tool_loader")

    converted_tools: list[FunctionTool] = []
    set_tracing_disabled(True)  # Avoid SDK logging noise for transient connect attempts
    try:
        for server in servers:

            async def _fetch_tools(current_server: MCPServer = server) -> list[FunctionTool]:
                manager = default_mcp_manager
                registered = manager.register(current_server) if hasattr(manager, "register") else current_server
                if hasattr(manager, "ensure_connected"):
                    await manager.ensure_connected(registered)
                try:
                    if getattr(registered, "session", None) is None:
                        await registered.connect()  # type: ignore[call-arg]
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "Optional direct connect attempt failed for %s", getattr(registered, "name", registered)
                    )

                proxy_type = LoopAffineAsyncProxy
                is_proxy_instance = isinstance(proxy_type, type) and isinstance(registered, proxy_type)
                if is_proxy_instance:
                    server_for_tools: MCPServer = registered
                else:
                    try:
                        server_for_tools = LoopAffineAsyncProxy(registered, manager)  # type: ignore[arg-type]
                    except Exception:
                        server_for_tools = registered

                return await MCPUtil.get_function_tools(
                    server_for_tools,
                    convert_schemas_to_strict,
                    run_context,
                    agent_for_fetch,
                )

            tools_for_server: list[FunctionTool] = _run_coroutine_from_factory(_fetch_tools)
            converted_tools.extend(tools_for_server)
    finally:
        set_tracing_disabled(False)

    return converted_tools


__all__ = ["from_mcp"]


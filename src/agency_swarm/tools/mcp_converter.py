"""MCP server to tool conversion utilities."""

import asyncio
import contextvars
import logging
import threading
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Union

from agents import Agent as SDKAgent, FunctionTool, default_tool_error_function, set_tracing_disabled
from agents.mcp.server import MCPServer
from agents.mcp.util import MCPUtil
from agents.run_context import RunContextWrapper

from agency_swarm.tools.mcp_manager import _bind_persistent_servers, default_mcp_manager

if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent as AgencyAgent

logger = logging.getLogger(__name__)


def _run_coroutine_from_factory(factory: Callable[[], Awaitable[Any]]) -> Any:
    """Execute an async coroutine factory from synchronous code."""
    caller_context = contextvars.copy_context()
    result: dict[str, Any] = {}
    error: list[BaseException] = []

    def _runner() -> None:
        try:
            result["value"] = caller_context.run(lambda: asyncio.run(factory()))  # type: ignore[arg-type]
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
    convert_schemas_to_strict: bool = False,
    context: RunContextWrapper[Any] | None = None,
    agent: Union["AgencyAgent", SDKAgent, None] = None,
) -> list[FunctionTool]:
    """
    Convert MCP servers into FunctionTool instances.

    Tool discovery and error formatting are delegated to the Agents SDK
    (``MCPUtil.get_function_tools`` with ``failure_error_function``); what stays custom is
    persistence-key registration, loop-affine proxies, and the sync facade.

    Args:
        mcp_servers: List of MCP servers to convert
        convert_schemas_to_strict: Whether to convert schemas to strict mode
        context: Run context wrapper
        agent: Agent instance

    Returns:
        List of FunctionTool instances
    """
    if not mcp_servers:
        return []

    servers = _bind_persistent_servers(list(mcp_servers))
    run_context = context or RunContextWrapper(context=None)
    agent_for_fetch: SDKAgent
    if isinstance(agent, SDKAgent):
        agent_for_fetch = agent
    else:
        agent_for_fetch = SDKAgent(name="mcp_tool_loader")

    # Ensure each server's worker exists and non-OAuth servers are connected (synchronous)
    for srv in servers:
        default_mcp_manager._ensure_driver(getattr(srv, "_server", srv))

    # Save the current tracing state before disabling it
    # The SDK doesn't expose a public getter, so we access the internal provider state
    # This is necessary to avoid permanently re-enabling tracing if it was already disabled
    from agents.tracing import get_trace_provider

    trace_provider = get_trace_provider()
    original_tracing_disabled = getattr(trace_provider, "_disabled", False)

    # Temporarily disable tracing to avoid sdk logging a non-existent error
    set_tracing_disabled(True)
    try:

        async def _fetch_tools() -> list[FunctionTool]:
            tools: list[FunctionTool] = []
            for server in servers:
                server_tools = await MCPUtil.get_function_tools(
                    server,
                    convert_schemas_to_strict,
                    run_context,
                    agent_for_fetch,
                    failure_error_function=default_tool_error_function,
                )
                tools.extend(t for t in server_tools if isinstance(t, FunctionTool))
            return tools

        return _run_coroutine_from_factory(_fetch_tools)
    finally:
        # Restore the original tracing state instead of unconditionally enabling it
        set_tracing_disabled(original_tracing_disabled)

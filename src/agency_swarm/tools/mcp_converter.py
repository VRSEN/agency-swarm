"""MCP server to tool conversion utilities."""

import asyncio
import functools
import logging
import threading
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Union

from agents import Agent as SDKAgent, FunctionTool, default_tool_error_function, set_tracing_disabled
from agents.mcp.server import MCPServer
from agents.mcp.util import MCPUtil
from agents.run_context import RunContextWrapper
from agents.tool import ToolContext

from agency_swarm.tools.mcp_manager import LoopAffineAsyncProxy, default_mcp_manager

if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent as AgencyAgent

logger = logging.getLogger(__name__)


def _with_error_handling(tool: FunctionTool) -> FunctionTool:
    """Wrap an MCP FunctionTool to catch exceptions and return error strings.

    This makes MCP tools behave like @function_tool decorated functions,
    which return error messages to the agent instead of propagating exceptions.
    """
    original_invoke = tool.on_invoke_tool

    @functools.wraps(original_invoke)
    async def wrapped_invoke(ctx: ToolContext[Any], input_json: str) -> Any:
        try:
            return await original_invoke(ctx, input_json)
        except Exception as e:
            logger.warning(f"MCP tool '{tool.name}' failed: {e}")
            return default_tool_error_function(ctx, e)

    tool.on_invoke_tool = wrapped_invoke
    return tool


def _run_coroutine_from_factory(factory: Callable[[], Awaitable[Any]]) -> Any:
    """Execute an async coroutine factory from synchronous code."""
    result: dict[str, Any] = {}
    error: list[BaseException] = []

    def _runner() -> None:
        try:
            coro = factory()
            result["value"] = asyncio.run(coro)  # type: ignore[arg-type]
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

    servers = list(mcp_servers)
    run_context = context or RunContextWrapper(context=None)
    agent_for_fetch: SDKAgent
    if isinstance(agent, SDKAgent):
        agent_for_fetch = agent
    else:
        agent_for_fetch = SDKAgent(name="mcp_tool_loader")

    # Register servers
    server_names = []
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

    # Wrap servers in LoopAffineAsyncProxy and ensure drivers are created
    for idx, srv in enumerate(list(servers)):
        if not isinstance(srv, LoopAffineAsyncProxy):
            proxy = LoopAffineAsyncProxy(srv, default_mcp_manager)
            servers[idx] = proxy  # type: ignore[assignment,call-overload]
            srv = proxy  # type: ignore[assignment]

        # Ensure driver is created and connected on the background loop (synchronous)
        default_mcp_manager._ensure_driver(getattr(srv, "_server", srv))

    converted_tools: list[FunctionTool] = []

    # Save the current tracing state before disabling it
    # The SDK doesn't expose a public getter, so we access the internal provider state
    # This is necessary to avoid permanently re-enabling tracing if it was already disabled
    from agents.tracing import get_trace_provider

    trace_provider = get_trace_provider()
    original_tracing_disabled = getattr(trace_provider, "_disabled", False)

    # Temporarily disable tracing to avoid sdk logging a non-existent error
    set_tracing_disabled(True)
    try:
        for server in servers:

            async def _fetch_tools(current_server: MCPServer = server) -> list[FunctionTool]:
                tools = await MCPUtil.get_function_tools(
                    current_server,
                    convert_schemas_to_strict,
                    run_context,
                    agent_for_fetch,
                )
                return [t for t in tools if isinstance(t, FunctionTool)]

            function_tools: list[FunctionTool] = _run_coroutine_from_factory(_fetch_tools)
            # Wrap each tool with error handling so exceptions return as strings to the agent
            wrapped_tools = [_with_error_handling(t) for t in function_tools]
            converted_tools.extend(wrapped_tools)
    finally:
        # Restore the original tracing state instead of unconditionally enabling it
        set_tracing_disabled(original_tracing_disabled)

    return converted_tools

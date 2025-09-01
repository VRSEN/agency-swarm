import inspect
import json
import logging
import os
import sys
from typing import Any

from agents.run_context import RunContextWrapper
from agents.tool import FunctionTool
from agents.tool_context import ToolContext
from fastmcp import FastMCP
from fastmcp.exceptions import McpError
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.server import Transport
from fastmcp.tools.tool import Tool, ToolResult
from mcp.types import ErrorData

from agency_swarm.tools import BaseTool, ToolFactory

logger = logging.getLogger(__name__)


def _load_tools_from_directory(tools_dir: str) -> list[type[BaseTool] | FunctionTool]:
    """Load BaseTool classes and FunctionTool instances from a directory."""
    tools: list[type[BaseTool] | FunctionTool] = []

    # Add tools directory to Python path if it's not already there
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)

    # Find all Python files in the tools directory
    for root, _, files in os.walk(tools_dir):
        for file in files:
            if file.endswith(".py") and not file.startswith("__"):
                module_path = os.path.join(root, file)
                file_tools = ToolFactory.from_file(module_path)
                tools.extend(file_tools)

    return tools


def run_mcp(
    tools: list[type[BaseTool] | FunctionTool] | str,
    host: str = "0.0.0.0",
    port: int = 8000,
    app_token_env: str | None = "APP_TOKEN",
    server_name: str = "mcp-tools-server",
    return_app: bool = False,
    transport: Transport = "streamable-http",
):
    """
    Launch a FastMCP server exposing BaseTool and FunctionTool instances.
    Args:
        tools: List of BaseTool/FunctionTool classes or path to directory containing tools.
        host: Host to bind the server to.
        port: Port to bind the server to.
        app_token_env: Environment variable name for authentication token. Provide None to disable authentication.
        server_name: Name identifier for the MCP server
        return_app: If True, returns the FastMCP instance instead of running it.
        transport: Mcp transport protocol to use.
    Returns:
        FastMCP instance if return_app=True, otherwise None
    """
    app_token_env = app_token_env or ""
    # Handle tools input - either list of classes or directory path
    if isinstance(tools, str):
        # It's a directory path
        tools_list = _load_tools_from_directory(tools)
        if not tools_list:
            raise ValueError(f"No BaseTool classes found in directory: {tools}")
        logger.info(f"Found {len(tools_list)} tools in {tools}")
    else:
        # It's a list of tool classes
        tools_list = tools
        if not tools_list or len(tools_list) == 0:
            raise ValueError("No tools provided. Please provide at least one tool class.")

    # stateless_http is required for oai agents
    mcp: FastMCP = FastMCP(server_name, stateless_http=True)

    # Get authentication token
    app_token = os.getenv(app_token_env)
    if app_token is None or app_token == "":
        logger.warning(f"{app_token_env} is not set. Authentication will be disabled.")
    else:
        if transport == "stdio":
            logger.warning("Stdio servers do not support authentication.")
        else:

            class StaticBearer(Middleware):
                def __init__(self, token: str) -> None:
                    self.expected = f"Bearer {token}"

                async def on_request(self, ctx: MiddlewareContext, call_next):
                    hdrs = get_http_headers()
                    if hdrs.get("authorization") != self.expected:
                        error = ErrorData(code=401, message="Unauthorized")
                        raise McpError(error)
                    return await call_next(ctx)

                async def on_read_resource(self, ctx: MiddlewareContext, call_next):
                    hdrs = get_http_headers()
                    if hdrs.get("authorization") != self.expected:
                        error = ErrorData(code=401, message="Unauthorized")
                        raise McpError(error)
                    return await call_next(ctx)

            mcp.add_middleware(StaticBearer(app_token))

    tool_registry = {}

    for tool in tools_list:
        if inspect.isclass(tool):
            # For BaseTool classes, use __name__
            tool_name = getattr(tool, "name", None) or tool.__name__
        else:
            # For FunctionTool instances, use the name attribute
            tool_name = getattr(tool, "name", None) or "unknown_tool"
        if tool_name in tool_registry:
            raise ValueError(f"Duplicate tool name detected: {tool_name}. Please use a different tool name.")
        tool_registry[tool_name] = tool
        logger.info(f"Registered tool: {tool_name}")

    for _tool_name, tool_obj in tool_registry.items():
        # Handle different tool types
        if inspect.isclass(tool_obj) and issubclass(tool_obj, BaseTool):
            logger.info(f"Converting BaseTool: {tool_obj}")
            tool_obj = ToolFactory.adapt_base_tool(tool_obj)

        # on_invoke_tool does not contain input type hints
        # Create a custom tool to maintain input schema
        if isinstance(tool_obj, FunctionTool):
            # Create a custom tool class that extends Tool
            class CustomTool(Tool):
                _function_tool: FunctionTool  # Declare the attribute for MyPy

                def __init__(self, function_tool):
                    super().__init__(
                        key=function_tool.name,
                        name=function_tool.name,
                        description=function_tool.description,
                        parameters=function_tool.params_json_schema,  # Use existing JSON schema directly
                        enabled=True,
                    )
                    # Store the function_tool reference after super().__init__
                    object.__setattr__(self, "_function_tool", function_tool)

                async def run(self, arguments: dict[str, Any]) -> ToolResult:
                    # Convert to JSON string format expected by FunctionTool
                    args_json = json.dumps(arguments)

                    # Create a minimal ToolContext for the FunctionTool
                    # Since we're in MCP environment, create a dummy context
                    # SDK v0.2.x requires passing a tool_call with the tool name
                    from openai.types.responses.response_function_tool_call import ResponseFunctionToolCall

                    tool_call = ResponseFunctionToolCall(
                        call_id=f"mcp_call_{self.name}", name=self.name, type="function_call", arguments=args_json
                    )

                    tool_context = ToolContext.from_agent_context(
                        RunContextWrapper(context={}), tool_call_id=f"mcp_call_{self.name}", tool_call=tool_call
                    )

                    # Call the original tool function
                    result = await self._function_tool.on_invoke_tool(tool_context, args_json)
                    return ToolResult(content=result)

            # Create and add the custom tool
            custom_tool = CustomTool(tool_obj)
            mcp.add_tool(custom_tool)
        else:
            # For non-FunctionTool instances, fall back to the decorator approach
            raise ValueError(f"Unexpected tool type: {type(tool_obj)} for tool: {_tool_name}")

    if return_app:
        return mcp

    if transport == "stdio":
        mcp.run(transport=transport)
    else:
        mcp.run(transport=transport, host=host, port=port)

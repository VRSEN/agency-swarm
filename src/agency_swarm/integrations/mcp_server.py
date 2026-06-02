import inspect
import json
import logging
import os
import sys
from typing import Any, Literal

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

HTTPTransport = Literal["http", "streamable-http", "sse"]


def _default_stateless_http(transport: Transport | None, stateless_http: bool | None) -> bool | None:
    if stateless_http is not None:
        return stateless_http
    if transport == "sse":
        return False
    if transport in {None, "http", "streamable-http"}:
        return True
    return stateless_http


class OpenAIAgentsFastMCP(FastMCP):
    """FastMCP server that keeps OpenAI Agents HTTP clients stateless by default."""

    async def run_http_async(
        self,
        show_banner: bool = True,
        transport: HTTPTransport = "http",
        host: str | None = None,
        port: int | None = None,
        log_level: str | None = None,
        path: str | None = None,
        uvicorn_config: dict[str, Any] | None = None,
        middleware: list[Any] | None = None,
        json_response: bool | None = None,
        stateless_http: bool | None = None,
        stateless: bool | None = None,
    ) -> None:
        if stateless is not None and stateless_http is None:
            stateless_http = stateless
        stateless_http = _default_stateless_http(transport, stateless_http)
        await super().run_http_async(
            show_banner=show_banner,
            transport=transport,
            host=host,
            port=port,
            log_level=log_level,
            path=path,
            uvicorn_config=uvicorn_config,
            middleware=middleware,
            json_response=json_response,
            stateless_http=stateless_http,
            stateless=stateless,
        )

    def http_app(
        self,
        path: str | None = None,
        middleware: list[Any] | None = None,
        json_response: bool | None = None,
        stateless_http: bool | None = None,
        transport: HTTPTransport = "http",
        event_store: Any = None,
        retry_interval: int | None = None,
    ) -> Any:
        stateless_http = _default_stateless_http(transport, stateless_http)
        return super().http_app(
            path=path,
            middleware=middleware,
            json_response=json_response,
            stateless_http=stateless_http,
            transport=transport,
            event_store=event_store,
            retry_interval=retry_interval,
        )


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
    uvicorn_config: dict[str, Any] | None = None,
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
        uvicorn_config: Optional Uvicorn config overrides (HTTP/SSE transports only).
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

    mcp: FastMCP = OpenAIAgentsFastMCP(server_name)

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
                        name=function_tool.name,
                        description=function_tool.description,
                        parameters=function_tool.params_json_schema,  # Use existing JSON schema directly
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
        # Stateless HTTP is required for OpenAI Agents clients. FastMCP v3 moved
        # this option from the constructor to HTTP run/app helpers. SSE does not
        # support stateless mode.
        run_kwargs: dict[str, Any] = {
            "transport": transport,
            "host": host,
            "port": port,
            "uvicorn_config": uvicorn_config,
        }
        if transport != "sse":
            run_kwargs["stateless_http"] = True
        else:
            run_kwargs["stateless_http"] = False
        mcp.run(**run_kwargs)

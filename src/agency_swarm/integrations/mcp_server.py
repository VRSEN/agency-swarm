import asyncio
import inspect
import json
import logging
import os
from typing import Any, List, Type, Union

from agents.strict_schema import ensure_strict_json_schema
from agents.tool import FunctionTool
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import McpError
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.server import Transport
from fastmcp.tools.tool import Tool, ToolResult
from mcp.types import ErrorData

from agency_swarm import BaseTool

logger = logging.getLogger(__name__)
load_dotenv()

def run_mcp(
    tools: List[Union[Type[BaseTool], Type[FunctionTool]]],
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
        tools: List of BaseTool/FunctionTool classes
        host: Host to bind the server to.
        port: Port to bind the server to.
        app_token_env: Environment variable name for authentication token. Provide None to disable authentication.
        server_name: Name identifier for the MCP server
        return_app: If True, returns the FastMCP instance instead of running it.
        transport: Mcp transport protocol to use.
    Returns:
        FastMCP instance if return_app=True, otherwise None
    """
    if not tools or len(tools) == 0:
        raise ValueError("No tools provided. Please provide at least one tool class.")

    # stateless_http is required for oai agents
    mcp = FastMCP(server_name, stateless_http=True)

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

    for tool in tools:
        tool_name = getattr(tool, 'name', None) or tool.__name__
        if tool_name in tool_registry:
            raise ValueError(f"Duplicate tool name detected: {tool_name}. Please use a different tool name.")
        tool_registry[tool_name] = tool
        logger.info(f"Registered tool: {tool_name}")

    for tool_name, tool in tool_registry.items():
        # Handle different tool types
        if inspect.isclass(tool) and issubclass(tool, BaseTool):
            logger.info(f"Converting BaseTool: {tool}")
            tool = _adapt_legacy_tool(tool)

        # on_invoke_tool does not contain input type hints
        # Create a custom tool to maintain input schema
        if isinstance(tool, FunctionTool):

            # Create a custom tool class that extends Tool
            class CustomTool(Tool):
                def __init__(self, function_tool):
                    super().__init__(
                        key=function_tool.name,
                        name=function_tool.name,
                        description=function_tool.description,
                        parameters=function_tool.params_json_schema,  # Use your existing JSON schema directly
                        enabled=True
                    )
                    # Store the function_tool reference after super().__init__
                    object.__setattr__(self, '_function_tool', function_tool)

                async def run(self, arguments: dict[str, Any]) -> ToolResult:
                    # Convert to JSON string format expected by FunctionTool
                    args_json = json.dumps(arguments)
                    # Call the original tool function
                    result = await self._function_tool.on_invoke_tool(None, args_json)
                    return ToolResult(content=result)

            # Create and add the custom tool
            custom_tool = CustomTool(tool)
            mcp.add_tool(custom_tool)
        else:
            # For non-FunctionTool instances, fall back to the decorator approach
            raise ValueError(f"Unexpected tool type: {type(tool)} for tool: {tool.name}")

    if return_app:
        return mcp

    if transport == "stdio":
        mcp.run(transport=transport)
    else:
        mcp.run(transport=transport, host=host, port=port)

def _adapt_legacy_tool(legacy_tool: type[BaseTool]):
        """
        Adapts a legacy BaseTool (class-based) to a FunctionTool (function-based).
        Args:
            legacy_tool: A class inheriting from BaseTool.
        Returns:
            A FunctionTool instance.
        """
        name = legacy_tool.__name__
        description = legacy_tool.__doc__ or ""
        if bool(getattr(legacy_tool, "__abstractmethods__", set())):
            raise TypeError(f"Legacy tool '{name}' must implement all abstract methods.")
        if description == "":
            logger.warning(f"Warning: Tool {name} has no docstring.")
        # Use the Pydantic model schema for parameters
        params_json_schema = legacy_tool.model_json_schema()
        if legacy_tool.ToolConfig.strict:
            params_json_schema = ensure_strict_json_schema(params_json_schema)
        # Remove title/description at the top level, keep only in properties
        params_json_schema = {k: v for k, v in params_json_schema.items() if k not in ("title", "description")}
        params_json_schema["additionalProperties"] = False

        # The on_invoke_tool function
        async def on_invoke_tool(ctx: Any, input_json: str):
            # Parse input_json to dict
            import json

            try:
                args = json.loads(input_json) if input_json else {}
            except Exception as e:
                return f"Error: Invalid JSON input: {e}"
            try:
                # Instantiate the legacy tool with args
                tool_instance = legacy_tool(**args)
                if inspect.iscoroutinefunction(tool_instance.run):
                    result = await tool_instance.run()
                else:
                    # Always run sync run() in a thread for async compatibility
                    result = await asyncio.to_thread(tool_instance.run)
                return str(result)
            except Exception as e:
                return f"Error running legacy tool: {e}"

        return FunctionTool(
            name=name,
            description=description.strip(),
            params_json_schema=params_json_schema,
            on_invoke_tool=on_invoke_tool,
            strict_json_schema=legacy_tool.ToolConfig.strict,
        )

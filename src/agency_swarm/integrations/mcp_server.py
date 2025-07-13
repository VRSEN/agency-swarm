import asyncio
import contextlib
import importlib
import inspect
import json
import logging
import os
import sys
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Type, Union

import mcp.types as types
import uvicorn
from agents.tool import FunctionTool
from dotenv import load_dotenv
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

from agency_swarm import BaseTool

load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)


def _load_tools_from_directory(tools_dir: str) -> List[type[BaseTool]]:
    """Load BaseTool classes from a directory."""
    tools: List[type[BaseTool]] = []

    # Add tools directory to Python path if it's not already there
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)

    # Find all Python files in the tools directory
    for root, _, files in os.walk(tools_dir):
        for file in files:
            if file.endswith('.py') and not file.startswith('__'):
                module_path = os.path.join(root, file)
                module_name = os.path.splitext(file)[0]

                # Import the module
                try:
                    spec = importlib.util.spec_from_file_location(module_name, module_path)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)

                        # Find BaseTool subclasses in the module
                        for item_name, item in inspect.getmembers(module):
                            if (inspect.isclass(item) and 
                                issubclass(item, BaseTool) and 
                                item != BaseTool):
                                tools.append(item)
                except Exception as e:
                    logger.error(f"Could not load module {module_name}: {e}")

    return tools

def _verify_token(request: Request, app_token: Optional[str]) -> bool:
    """Simple token verification - returns True if authenticated, False otherwise"""
    if app_token is None or app_token == "":
        return True  # No auth required

    # Check for Authorization header
    authorization = request.headers.get("authorization")
    if not authorization:
        return False

    try:
        scheme, credentials = authorization.split()
        if scheme.lower() != "bearer":
            return False

        return credentials == app_token
    except ValueError:
        return False

def run_mcp(
    tools: Union[List[Union[Type[BaseTool], Type[FunctionTool]]], str],
    host: str = "0.0.0.0",
    port: int = 8000,
    app_token_env: str = "APP_TOKEN",
    server_name: str = "mcp-tools-server",
    cors_origins: List[str] = ["*"],
    return_app: bool = False,
):
    """
    Launch an MCP (Model Context Protocol) server exposing BaseTool instances.

    Args:
        tools: List of FunctionTool or BaseTool classes OR path to directory containing BaseTool modules
        host: Host to bind the server to. Only used if return_app is False.
        port: Port to bind the server to. Only used if return_app is False.
        app_token_env: Environment variable name for authentication token
        server_name: Name identifier for the MCP server
        cors_origins: List of allowed CORS origins
        return_app: If False, runs the server automatically.
        If True, return the Starlette app instead of running it.

    Returns:
        Starlette app if return_app=True, otherwise None
    """

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
            raise ValueError("No tools provided. Please provide at least one BaseTool class.")

    # Get authentication token
    app_token = os.getenv(app_token_env)
    if app_token is None or app_token == "":
        logger.warning(f"{app_token_env} is not set. Authentication will be disabled.")

    # Create thread pool for sync tools
    max_workers = int(os.getenv("TOOL_THREAD_POOL_SIZE", min(32, (os.cpu_count() or 1) + 4)))
    if not os.getenv("TOOL_THREAD_POOL_SIZE"):
        logger.warning(f"TOOL_THREAD_POOL_SIZE env variable is not set. Defaulting to {max_workers} max workers.")
    thread_pool = ThreadPoolExecutor(max_workers=max_workers)

    # Create tool registry
    tool_registry = {}

    # Register tools
    for tool in tools_list:
        tool_name = tool.name if isinstance(tool, FunctionTool) else tool.__name__
        if tool_name in tool_registry:
            raise ValueError(f"Duplicate tool name detected: {tool_name}. Please use a different tool name.")
        tool_registry[tool_name] = tool
        logger.info(f"Registered tool: {tool_name}")

    def create_mcp_server() -> Server:
        """Create MCP server with registered tools"""
        app = Server(server_name)

        @app.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
            """Handle tool calls with proper error handling"""
            try:
                # Find the registered tool
                if name not in tool_registry:
                    logger.error(f"Unknown tool requested: {name}")
                    return [
                        types.TextContent(
                            type="text",
                            text=f"Error: Unknown tool '{name}'. Available tools: {list(tool_registry.keys())}",
                        )
                    ]

                tool = tool_registry[name]

                # Validate arguments against tool schema
                if isinstance(tool, FunctionTool):
                    result = await tool.on_invoke_tool(ctx=None, input=json.dumps(arguments))
                else:
                    try:
                        tool_instance = tool(**arguments)
                    except Exception as e:
                        logger.error(f"Invalid arguments for tool {name}: {e}")
                        return [
                            types.TextContent(type="text", text=f"Error: Invalid arguments for tool '{name}': {str(e)}")
                        ]

                    # Execute tool
                    if asyncio.iscoroutinefunction(tool_instance.run):
                        result = await tool_instance.run()
                    else:
                        # Run sync tool in thread pool to avoid blocking
                        loop = asyncio.get_event_loop()
                        result = await loop.run_in_executor(thread_pool, tool_instance.run)

                logger.info(f"Successfully executed tool: {name}")
                return [types.TextContent(type="text", text=str(result))]

            except Exception as e:
                logger.error(f"Error executing tool {name}: {e}", exc_info=True)
                return [types.TextContent(type="text", text=f"Error executing tool '{name}': {str(e)}")]

        @app.list_tools()
        async def list_tools() -> list[types.Tool]:
            """Generate tool list from registered tool instances"""
            tools_list = []

            try:
                for tool_name, tool in tool_registry.items():
                    # Get the schema from the BaseTool
                    schema = tool.params_json_schema if isinstance(tool, FunctionTool) else tool.model_json_schema()

                    # Get description from docstring
                    description = tool.description if isinstance(tool, FunctionTool) else tool.__doc__ or f"Tool: {tool_name}"
                    description = description.strip()

                    # Create the MCP tool
                    tools_list.append(types.Tool(name=tool_name, description=description, inputSchema=schema))

                logger.info(f"Listed {len(tools_list)} available tools")
                return tools_list

            except Exception as e:
                logger.error(f"Error listing tools: {e}", exc_info=True)
                return []

        return app

    def create_app():
        """Create the production-ready ASGI application"""
        # Create MCP server
        mcp_server = create_mcp_server()

        # Middleware stack
        middleware = [
            Middleware(
                CORSMiddleware,
                allow_origins=cors_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        ]

        # Create session manager
        session_manager = StreamableHTTPSessionManager(
            app=mcp_server,
            json_response=True,  # Use JSON for non-streaming
            stateless=True,
        )

        async def handle_mcp(scope: Scope, receive: Receive, send: Send) -> None:
            """Handle MCP requests with authentication"""
            request = Request(scope, receive)

            # Simple token verification
            if not _verify_token(request, app_token):
                response = JSONResponse(
                    {"error": "Authentication required"}, status_code=401, headers={"WWW-Authenticate": "Bearer"}
                )
                await response(scope, receive, send)
                return

            try:
                await session_manager.handle_request(scope, receive, send)
            except Exception as e:
                logger.error(f"Error handling MCP request: {e}", exc_info=True)
                response = JSONResponse({"error": "Internal server error"}, status_code=500)
                await response(scope, receive, send)

        @contextlib.asynccontextmanager
        async def lifespan(app: Starlette) -> AsyncIterator[None]:
            """Application lifespan management"""
            try:
                async with session_manager.run():
                    logger.info(f"MCP server '{server_name}' started")
                    logger.info(f"Registered {len(tool_registry)} tools")
                    logger.info(f"Authentication: {'Enabled' if app_token else 'Disabled'}")
                    yield
            except Exception as e:
                logger.error(f"Error during server startup: {e}", exc_info=True)
                raise
            finally:
                logger.info("Shutting down MCP server...")
                # Shutdown thread pool to prevent thread leaks
                try:
                    thread_pool.shutdown(wait=True)
                    logger.info("Thread pool shut down successfully")
                except Exception as e:
                    logger.error(f"Error shutting down thread pool: {e}", exc_info=True)

        # Fastapi interferes with session manager, so use Starlette directly
        return Starlette(
            routes=[
                Mount("/mcp", app=handle_mcp),
            ],
            lifespan=lifespan,
            middleware=middleware,
        )

    app = create_app()

    if return_app:
        return app

    logger.info(f"MCP server running at http://{host}:{port}/mcp")

    try:
        uvicorn.run(
            app,
            host=host,
            port=port,
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise
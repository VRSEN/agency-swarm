import abc
import asyncio
import logging
import os
import tempfile
import threading
import time
from concurrent.futures import Future
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Type

from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp import Tool as MCPTool
from mcp.client.sse import sse_client
from mcp.client.streamable_http import GetSessionIdCallback, streamablehttp_client
from mcp.shared.message import SessionMessage
from mcp.types import CallToolResult, JSONRPCMessage
from pydantic import BaseModel
from typing_extensions import NotRequired, TypedDict

logger = logging.getLogger(__name__)


class AgentsException(Exception):
    """Base class for all exceptions in the Agents SDK."""


class UserError(AgentsException):
    """Exception raised when the user makes an error using the SDK."""

    message: str

    def __init__(self, message: str):
        self.message = message


# Template for adding pre-loaded tools to MCP server
class MCPToolParams(BaseModel):
    """Model to be used for pre-loaded MCP tools."""

    name: str
    description: Optional[str] = None
    inputSchema: Dict[str, Any] | Type[BaseModel]


class MCPServer(abc.ABC):
    """Base class for Model Context Protocol servers."""

    @abc.abstractmethod
    async def connect(self):
        """Connect to the server. For example, this might mean spawning a subprocess or
        opening a network connection. The server is expected to remain connected until
        `cleanup()` is called.
        """
        pass

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """A readable name for the server."""
        pass

    @property
    @abc.abstractmethod
    def strict(self) -> bool:
        """Use strict mode for the OpenAI's structured outputs."""
        pass

    @abc.abstractmethod
    async def cleanup(self):
        """Cleanup the server. For example, this might mean closing a subprocess or
        closing a network connection.
        """
        pass

    @abc.abstractmethod
    async def list_tools(self) -> list[MCPTool]:
        """List the tools available on the server."""
        pass

    @abc.abstractmethod
    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None) -> CallToolResult:
        """Invoke a tool on the server."""
        pass


class _MCPServerWithClientSession(MCPServer, abc.ABC):
    """Base class for MCP servers that use a `ClientSession` to communicate with the server."""

    def __init__(
        self,
        cache_tools_list: bool,
        strict: bool = False,
        allowed_tools: list[str] | None = None,
        pre_loaded_tools: list[MCPToolParams] | None = None,
    ):
        """
        Args:
            cache_tools_list: Whether to cache the tools list. If `True`, the tools list will be
                cached and only fetched from the server once. If `False`, the tools list will be
                fetched from the server on each call to `list_tools()`. The cache can be invalidated
                by calling `invalidate_tools_cache()`. You should set this to `True` if you know the
                server will not change its tools list, because it can drastically improve latency
                (by avoiding a round-trip to the server every time).
            strict: Whether to use strict mode when converting MCP tools to OpenAI tools.
            allowed_tools: Optional list of tool names to allow. Restricts the tools selection to the provided list.
                Only used if pre_loaded_tools are not provided. Otherwise, this parameter is ignored.
            pre_loaded_tools: Allows to skip fetching tools from the server. If provided:
                1. Only tools within the list will be available to the agent,
                2. Tools will not be fetched from the server,
                3. Connection to the server will be delayed until first tool use.
                4. No schema validation will be performed, make sure provided schemas are compatible with the server.
        """
        self._initialized = False

        if allowed_tools and not pre_loaded_tools:
            logger.warning("allowed_tools are not used if pre_loaded_tools are provided")

        if pre_loaded_tools:
            # Store parameters for later initialization
            self._cache_tools_list = cache_tools_list
            # Set minimal attributes needed for lazy mode
            self.session = None
            self._strict = strict
            self._allowed_tools = allowed_tools
            self.pre_loaded_tools = pre_loaded_tools
        else:
            # Normal initialization
            self.init_server(cache_tools_list, strict, allowed_tools)

    def init_server(
        self,
        cache_tools_list: bool,
        strict: bool = False,
        allowed_tools: list[str] | None = None,
        pre_loaded_tools: list[MCPToolParams] | None = None,
    ):
        """Perform the actual server initialization."""
        self.session: ClientSession | None = None
        self.exit_stack: AsyncExitStack = AsyncExitStack()
        self._cleanup_lock: asyncio.Lock = asyncio.Lock()
        self._cache_tools_list = cache_tools_list
        self._strict = strict
        self._allowed_tools = allowed_tools
        self.pre_loaded_tools = pre_loaded_tools
        # The cache is always dirty at startup, so that we fetch tools at least once
        self._cache_dirty = True
        self._tools_list: list[MCPTool] | None = None
        self._sync_manager = None
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop = asyncio.new_event_loop()
        self._queue = asyncio.Queue()
        self._shutdown_event = threading.Event()
        self._ready_event = threading.Event()
        self._startup_exception = None  # Store startup exception for detailed error reporting
        self._thread.start()

        # Wait for the connection to be established before returning
        if not self._ready_event.wait(timeout=20):
            raise TimeoutError("Server initialization timed out")

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main())

    async def _main(self):
        """
        Main event loop for the background thread managing async MCP server operations.

        Handles initial connection, dispatches synchronous method calls (connect, list_tools, call_tool, cleanup)
        to their async counterparts, maintains proper cleanup and shutdown.
        """
        try:
            await self._connect_async()
            self._initialized = True
            self._ready_event.set()
            while True:
                item = await self._queue.get()
                if item == "SHUTDOWN":
                    break
                method, args, result_future, timeout = item
                try:
                    coro = getattr(self, f"_{method}_async")(*args)
                    result = await asyncio.wait_for(coro, timeout=timeout)
                    result_future.set_result(result)
                except asyncio.TimeoutError:
                    result_future.set_exception(TimeoutError(f"MCP server call '{method}' timed out after {timeout}s"))
                except Exception as e:
                    result_future.set_exception(e)

        except Exception as e:
            # Extract the root cause from ExceptionGroup if present
            root_exception = self._extract_root_exception(e)
            # Store the actual meaningful exception for detailed error reporting
            self._startup_exception = root_exception
            # If connection fails, still signal ready event to unblock waiting calls
            if not self._ready_event.is_set():
                self._ready_event.set()
            logger.error(f"Error in MCP server main loop: {root_exception}")
            return  # Do not raise exceptions here as it leads to loop halting

        finally:
            # Cleanup must happen while the event loop is still active
            await self._cleanup_async()
            self._initialized = False  # Server is no longer functional
            self._shutdown_event.set()

    @staticmethod
    def extract_error_from_log(log_file_path: str, errlog_handle=None) -> str | None:
        """
        Read and return the contents of the given log file, or an empty string if not found or empty.
        Deletes the file after reading. Closes the file handle if provided.
        """
        if errlog_handle is not None and not errlog_handle.closed:
            errlog_handle.close()
        if not os.path.exists(log_file_path):
            return None
        with open(log_file_path, "r", encoding="utf-8") as f:
            contents = f.read()
        # Try to delete the file, retrying if necessary
        start = time.time()
        while True:
            try:
                os.remove(log_file_path)
                break
            except PermissionError:
                if time.time() - start > 5.0:
                    logger.warning(f"Failed to delete log file after 5 seconds: {log_file_path}")
                    break
                time.sleep(0.2)
        return contents

    def _call_in_loop(self, method, *args, timeout=120):
        # Add a timeout to prevent indefinite hangs
        if not self._ready_event.wait(timeout=10):
            errlog = getattr(self, "_errlog_buffer", None)
            if errlog:
                error_message = self.extract_error_from_log(errlog.name, errlog)
                if error_message and error_message.strip() != "":
                    raise RuntimeError(error_message)
                else:
                    raise RuntimeError(
                        "Failed to connect to the server. Please check if the server is running and accessible."
                    )
            else:
                # SSE servers do not support error logging, print generic message
                raise RuntimeError(
                    "Failed to connect to the server. Please check if the server is running and accessible."
                )

        # Check if there was a startup exception
        if self._startup_exception is not None:
            raise RuntimeError(f"MCP server failed to start: {self._startup_exception}")

        # Check if the server is still initialized (event loop is still running)
        if not self._initialized:
            raise RuntimeError("MCP server is not running or has been shut down.")

        result_future = Future()
        self._loop.call_soon_threadsafe(self._queue.put_nowait, (method, args, result_future, timeout))
        return result_future.result()  # blocks until result is ready

    # Synchronous public methods
    def connect(self):
        self._ensure_initialized()
        return self._call_in_loop("connect", timeout=10)

    def list_tools(self):
        if self.pre_loaded_tools:
            return self.pre_loaded_tools
        self._ensure_initialized()
        return self._call_in_loop("list_tools", timeout=10)

    def call_tool(self, tool_name, arguments, timeout=120):
        self._ensure_initialized()
        return self._call_in_loop("call_tool", tool_name, arguments, timeout=timeout)

    # TODO: Adjust cleanup to avoid http server warnings
    def cleanup(self):
        # Loop might not be initialized yet
        if hasattr(self, "_loop"):
            self._loop.call_soon_threadsafe(self._queue.put_nowait, "SHUTDOWN")
            self._shutdown_event.wait()
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join()
            if (errlog := getattr(self, "_errlog_buffer", None)) is not None:
                self.extract_error_from_log(errlog.name, errlog)  # Delete the error log file

    # Async implementations
    async def _connect_async(self):
        try:
            # For HTTP clients, ensure we give enough time for the connection to establish
            # and handle any initial connection retries that the client might need
            transport = await self.exit_stack.enter_async_context(self.create_streams())
            read, write = transport[:2]  # Take only first 2 values(ignore get_session_id from http server)
            session = await self.exit_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self.session = session
        except asyncio.TimeoutError:
            logger.error("Session initialization timed out")
            await self._cleanup_async()
            raise
        except Exception as e:
            logger.error(f"Error initializing MCP server: {e}")
            await self._cleanup_async()
            raise

    async def _list_tools_async(self) -> list[MCPTool]:
        if not self.session:
            raise UserError("Server not initialized. Make sure you call `connect()` first.")

        try:
            # Return from cache if caching is enabled, we have tools, and the cache is not dirty
            if self._cache_tools_list and not self._cache_dirty and self._tools_list:
                tools = self._tools_list
            else:
                # Reset the cache dirty to False
                self._cache_dirty = False
                # Fetch the tools from the server
                self._tools_list = (await self.session.list_tools()).tools
                tools = self._tools_list
        except Exception as e:
            # Check if it's a connection closed error and attempt to reconnect
            if self._is_connection_closed_error(e):
                logger.info(f"Connection closed, attempting to reconnect: {e}")
                await self._reconnect_async()
                # Retry the operation after reconnection
                if self._cache_tools_list and not self._cache_dirty and self._tools_list:
                    tools = self._tools_list
                else:
                    self._cache_dirty = False
                    self._tools_list = (await self.session.list_tools()).tools
                    tools = self._tools_list
            else:
                raise

        # Filter tools if allowed_tools is set
        if self._allowed_tools is not None:
            tools = [tool for tool in tools if getattr(tool, "name", None) in self._allowed_tools]
        return tools

    async def _call_tool_async(self, tool_name: str, arguments: dict[str, Any] | None) -> CallToolResult:
        if not self.session:
            raise UserError("Server not initialized. Make sure you call `connect()` first.")

        try:
            return await self.session.call_tool(tool_name, arguments)
        except Exception as e:
            # Check if it's a connection closed error and attempt to reconnect
            if self._is_connection_closed_error(e):
                logger.info(f"Connection closed, attempting to reconnect: {e}")
                await self._reconnect_async()
                # Retry the tool call after reconnection
                return await self.session.call_tool(tool_name, arguments)
            else:
                raise

    async def _cleanup_async(self):
        async with self._cleanup_lock:
            try:
                await self.exit_stack.aclose()
                self.session = None
            except Exception as e:
                logger.error(f"Error cleaning up server: {e}")

    @property
    def strict(self) -> bool:
        """Whether to use strict mode when converting MCP tools to OpenAI tools."""
        return self._strict

    @strict.setter
    def strict(self, value: bool):
        self._strict = value

    @property
    def allowed_tools(self) -> list[str] | None:
        return self._allowed_tools

    @allowed_tools.setter
    def allowed_tools(self, value: list[str] | None):
        self._allowed_tools = value

    @abc.abstractmethod
    def create_streams(
        self,
    ) -> AbstractAsyncContextManager[
        tuple[
            MemoryObjectReceiveStream[JSONRPCMessage | Exception],
            MemoryObjectSendStream[JSONRPCMessage],
        ]
    ]:
        """Create the streams for the server."""
        pass

    def invalidate_tools_cache(self):
        """Invalidate the tools cache."""
        self._cache_dirty = True

    def _is_connection_closed_error(self, exception: Exception) -> bool:
        """Check if the exception indicates a closed connection."""
        # Check for common connection closed errors
        error_types = [
            "ClosedResourceError",
            "ConnectionClosed",
            "ConnectionResetError",
            "BrokenPipeError",
            "ConnectionAbortedError",
        ]

        exception_name = type(exception).__name__
        exception_str = str(exception).lower()

        # Check if it's one of the known connection closed error types
        if exception_name in error_types:
            return True

        # Check if error message contains connection closed indicators
        closed_indicators = ["closed", "connection closed", "broken pipe", "connection reset", "connection aborted"]

        return any(indicator in exception_str for indicator in closed_indicators)

    async def _reconnect_async(self):
        """Reconnect to the server after a connection failure."""
        logger.info("Attempting to reconnect to MCP server")

        # Clean up the existing connection
        try:
            if self.session:
                await self.exit_stack.aclose()
                self.session = None
        except Exception as e:
            logger.warning(f"Error during cleanup before reconnect: {e}")

        # Reset the exit stack for new connection
        self.exit_stack = AsyncExitStack()

        # Re-establish the connection
        await self._connect_async()

        # Invalidate tools cache to ensure fresh data after reconnection
        self._cache_dirty = True

        logger.info("Successfully reconnected to MCP server")

    def _extract_root_exception(self, exception: Exception) -> Exception:
        """Extract the root cause exception from ExceptionGroups or return the original exception."""
        # Handle ExceptionGroup (Python 3.11+) or BaseExceptionGroup
        if hasattr(exception, "exceptions") and exception.exceptions:
            # Recursively extract from nested ExceptionGroups
            for sub_exception in exception.exceptions:
                if hasattr(sub_exception, "exceptions") and sub_exception.exceptions:
                    return self._extract_root_exception(sub_exception)
                else:
                    return sub_exception
        return exception

    def _ensure_initialized(self):
        """Ensure the server is initialized. If init_on_use was used, initialize now."""
        if not self._initialized:
            self.init_server(self._cache_tools_list, self._strict, self._allowed_tools, self.pre_loaded_tools)


class MCPServerStdioParams(TypedDict):
    """Mirrors `mcp.client.stdio.StdioServerParameters`, but lets you pass params without another
    import.
    """

    command: str
    """The executable to run to start the server. For example, `python` or `node`."""

    args: NotRequired[list[str]]
    """Command line args to pass to the `command` executable. For example, `['foo.py']` or
    `['server.js', '--port', '8080']`."""

    env: NotRequired[dict[str, str]]
    """The environment variables to set for the server. ."""

    cwd: NotRequired[str | Path]
    """The working directory to use when spawning the process."""

    encoding: NotRequired[str]
    """The text encoding used when sending/receiving messages to the server. Defaults to `utf-8`."""

    encoding_error_handler: NotRequired[Literal["strict", "ignore", "replace"]]
    """The text encoding error handler. Defaults to `strict`.

    See https://docs.python.org/3/library/codecs.html#codec-base-classes for
    explanations of possible values.
    """

    strict: NotRequired[bool]
    """Whether to use strict mode when converting MCP tools to OpenAI tools. Defaults to `False`."""


class MCPServerStdio(_MCPServerWithClientSession):
    """MCP server implementation that uses the stdio transport. See the [spec]
    (https://spec.modelcontextprotocol.io/specification/2024-11-05/basic/transports/#stdio) for
    details.
    """

    def __init__(
        self,
        params: MCPServerStdioParams,
        cache_tools_list: bool = False,
        name: str | None = None,
        strict: bool = False,
        allowed_tools: list[str] | None = None,
        pre_loaded_tools: list[MCPToolParams] | None = None,
    ):
        """Create a new MCP server based on the stdio transport.

        Args:
            params: The params that configure the server. This includes the command to run to
                start the server, the args to pass to the command, the environment variables to
                set for the server, the working directory to use when spawning the process, and
                the text encoding used when sending/receiving messages to the server.
            cache_tools_list: Whether to cache the tools list. If `True`, the tools list will be
                cached and only fetched from the server once. If `False`, the tools list will be
                fetched from the server on each call to `list_tools()`. The cache can be
                invalidated by calling `invalidate_tools_cache()`. You should set this to `True`
                if you know the server will not change its tools list, because it can drastically
                improve latency (by avoiding a round-trip to the server every time).
            name: A readable name for the server. If not provided, we'll create one from the
                command.
            strict: Use strict mode for the OpenAI's structured outputs. Defaults to `False`.
            allowed_tools: Optional list of tool names to allow. Restricts the tools selection to the provided list.
                Only used if pre_loaded_tools are not provided. Otherwise, this parameter is ignored.
            pre_loaded_tools: Allows to skip fetching tools from the server. If provided:
                1. Only tools within the list will be available to the agent,
                2. Tools will not be fetched from the server,
                3. Connection to the server will be delayed until first tool use.
                4. No schema validation will be performed, make sure provided schemas are compatible with the server.
        """
        # For backwards compatibility, if strict is not provided, check if it's in the params
        if not strict:
            if "strict" in params:
                print("Strict parameter is deprecated. Use the strict argument instead.")
            strict = params.pop("strict", False)

        self.params = StdioServerParameters(
            command=params["command"],
            args=params.get("args", []),
            env=params.get("env"),
            cwd=params.get("cwd"),
            encoding=params.get("encoding", "utf-8"),
            encoding_error_handler=params.get("encoding_error_handler", "strict"),
        )
        self._name = name or f"stdio: {self.params.command}"
        # Save error log in the local directory
        self._errlog_buffer = tempfile.NamedTemporaryFile(
            mode="w+", encoding="utf-8", delete=False, suffix=f"_{self._name}_stderr.log"
        )
        super().__init__(
            cache_tools_list,
            strict=strict,
            allowed_tools=allowed_tools,
            pre_loaded_tools=pre_loaded_tools,
        )

    def create_streams(
        self,
    ) -> AbstractAsyncContextManager[
        tuple[
            MemoryObjectReceiveStream[JSONRPCMessage | Exception],
            MemoryObjectSendStream[JSONRPCMessage],
        ]
    ]:
        """Create the streams for the server."""
        # Pass the error log buffer to stdio_client
        return stdio_client(self.params, errlog=self._errlog_buffer)

    @property
    def name(self) -> str:
        """A readable name for the server."""
        return self._name


class MCPServerSseParams(TypedDict):
    """Mirrors the params in`mcp.client.sse.sse_client`."""

    url: str
    """The URL of the server."""

    headers: NotRequired[dict[str, str]]
    """The headers to send to the server."""

    timeout: NotRequired[float]
    """The timeout for the HTTP request. Defaults to 5 seconds."""

    sse_read_timeout: NotRequired[float]
    """The timeout for the SSE connection, in seconds. Defaults to 5 minutes."""

    strict: NotRequired[bool]
    """Whether to use strict mode when converting MCP tools to OpenAI tools. Defaults to `False`."""


class MCPServerSse(_MCPServerWithClientSession):
    """MCP server implementation that uses the HTTP with SSE transport. See the [spec]
    (https://spec.modelcontextprotocol.io/specification/2024-11-05/basic/transports/#http-with-sse)
    for details.
    """

    def __init__(
        self,
        params: MCPServerSseParams,
        cache_tools_list: bool = False,
        name: str | None = None,
        strict: bool = False,
        allowed_tools: list[str] | None = None,
        pre_loaded_tools: list[MCPToolParams] | None = None,
    ):
        """Create a new MCP server based on the HTTP with SSE transport.

        Args:
            params: The params that configure the server. This includes the URL of the server,
                the headers to send to the server, the timeout for the HTTP request, and the
                timeout for the SSE connection.

            cache_tools_list: Whether to cache the tools list. If `True`, the tools list will be
                cached and only fetched from the server once. If `False`, the tools list will be
                fetched from the server on each call to `list_tools()`. The cache can be
                invalidated by calling `invalidate_tools_cache()`. You should set this to `True`
                if you know the server will not change its tools list, because it can drastically
                improve latency (by avoiding a round-trip to the server every time).

            name: A readable name for the server. If not provided, we'll create one from the
                URL.
            strict: Use strict mode for the OpenAI's structured outputs. Defaults to `False`.
            allowed_tools: Optional list of tool names to allow. Restricts the tools selection to the provided list.
                Only used if pre_loaded_tools are not provided. Otherwise, this parameter is ignored.
            pre_loaded_tools: Allows to skip fetching tools from the server. If provided:
                1. Only tools within the list will be available to the agent,
                2. Tools will not be fetched from the server,
                3. Connection to the server will be delayed until first tool use.
                4. No schema validation will be performed, make sure provided schemas are compatible with the server.
        """
        # For backwards compatibility, if strict is not provided, check if it's in the params
        if not strict:
            if "strict" in params:
                print("Strict parameter is deprecated. Use the strict argument instead.")
            strict = params.pop("strict", False)

        self.params = params
        self._name = name or f"sse: {self.params['url']}"
        super().__init__(
            cache_tools_list,
            strict=strict,
            allowed_tools=allowed_tools,
            pre_loaded_tools=pre_loaded_tools,
        )

    def create_streams(
        self,
    ) -> AbstractAsyncContextManager[
        tuple[
            MemoryObjectReceiveStream[JSONRPCMessage | Exception],
            MemoryObjectSendStream[JSONRPCMessage],
        ]
    ]:
        """Create the streams for the server."""
        return sse_client(
            url=self.params["url"],
            headers=self.params.get("headers", None),
            timeout=self.params.get("timeout", 5),
            sse_read_timeout=self.params.get("sse_read_timeout", 60 * 5),
        )

    @property
    def name(self) -> str:
        """A readable name for the server."""
        return self._name


class MCPServerStreamableHttpParams(TypedDict):
    """Mirrors the params in`mcp.client.streamable_http.streamablehttp_client`."""

    url: str
    """The URL of the server."""

    headers: NotRequired[dict[str, str]]
    """The headers to send to the server."""

    timeout: NotRequired[timedelta]
    """The timeout for the HTTP request. Defaults to 5 seconds."""

    sse_read_timeout: NotRequired[timedelta]
    """The timeout for the SSE connection, in seconds. Defaults to 5 minutes."""

    terminate_on_close: NotRequired[bool]
    """Terminate on close"""


class MCPServerStreamableHttp(_MCPServerWithClientSession):
    """MCP server implementation that uses the Streamable HTTP transport. See the [spec]
    (https://modelcontextprotocol.io/specification/2025-03-26/basic/transports#streamable-http)
    for details.
    """

    def __init__(
        self,
        params: MCPServerStreamableHttpParams,
        cache_tools_list: bool = False,
        name: str | None = None,
        strict: bool = False,
        allowed_tools: list[str] | None = None,
        pre_loaded_tools: list[MCPToolParams] | None = None,
    ):
        """Create a new MCP server based on the Streamable HTTP transport.

        Args:
            params: The params that configure the server. This includes the URL of the server,
                the headers to send to the server, the timeout for the HTTP request, and the
                timeout for the connection.

            cache_tools_list: Whether to cache the tools list. If `True`, the tools list will be
                cached and only fetched from the server once. If `False`, the tools list will be
                fetched from the server on each call to `list_tools()`. The cache can be
                invalidated by calling `invalidate_tools_cache()`. You should set this to `True`
                if you know the server will not change its tools list, because it can drastically
                improve latency (by avoiding a round-trip to the server every time).

            name: A readable name for the server. If not provided, we'll create one from the
                URL.
            strict: Use strict mode for the OpenAI's structured outputs. Defaults to `False`.
            allowed_tools: Optional list of tool names to allow. Restricts the tools selection to the provided list.
                Only used if pre_loaded_tools are not provided. Otherwise, this parameter is ignored.
            pre_loaded_tools: Allows to skip fetching tools from the server. If provided:
                1. Only tools within the list will be available to the agent,
                2. Tools will not be fetched from the server,
                3. Connection to the server will be delayed until first tool use.
                4. No schema validation will be performed, make sure provided schemas are compatible with the server.
        """
        # For backwards compatibility, if strict is not provided, check if it's in the params
        if not strict:
            if "strict" in params:
                print("Strict parameter is deprecated. Use the strict argument instead.")
            strict = params.pop("strict", False)

        self.params = params
        self._name = name or f"streamable_http: {self.params['url']}"

        super().__init__(
            cache_tools_list,
            strict=strict,
            allowed_tools=allowed_tools,
            pre_loaded_tools=pre_loaded_tools,
        )

    def create_streams(
        self,
    ) -> AbstractAsyncContextManager[
        tuple[
            MemoryObjectReceiveStream[SessionMessage | Exception],
            MemoryObjectSendStream[SessionMessage],
            GetSessionIdCallback | None,
        ]
    ]:
        """Create the streams for the server."""
        return streamablehttp_client(
            url=self.params["url"],
            headers=self.params.get("headers", None),
            timeout=self.params.get("timeout", timedelta(seconds=30)),
            sse_read_timeout=self.params.get("sse_read_timeout", timedelta(seconds=60 * 5)),
            terminate_on_close=self.params.get("terminate_on_close", True),
        )

    @property
    def name(self) -> str:
        """A readable name for the server."""
        return self._name

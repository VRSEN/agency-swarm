import abc
import asyncio
import logging
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from pathlib import Path
from typing import Any, Literal

from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp import Tool as MCPTool
from mcp.client.sse import sse_client
from mcp.types import CallToolResult, JSONRPCMessage
from typing_extensions import NotRequired, TypedDict
import threading
from concurrent.futures import Future


logger = logging.getLogger(__name__)


class AgentsException(Exception):
    """Base class for all exceptions in the Agents SDK."""


class UserError(AgentsException):
    """Exception raised when the user makes an error using the SDK."""

    message: str

    def __init__(self, message: str):
        self.message = message


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
    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any] | None
    ) -> CallToolResult:
        """Invoke a tool on the server."""
        pass


class _MCPServerWithClientSession(MCPServer, abc.ABC):
    """Base class for MCP servers that use a `ClientSession` to communicate with the server."""

    def __init__(self, cache_tools_list: bool, strict: bool = False, allowed_tools: list[str] | None = None):
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
        """
        self.session: ClientSession | None = None
        self.exit_stack: AsyncExitStack = AsyncExitStack()
        self._cleanup_lock: asyncio.Lock = asyncio.Lock()
        self.cache_tools_list = cache_tools_list
        self._strict = strict
        self._allowed_tools = allowed_tools
        # The cache is always dirty at startup, so that we fetch tools at least once
        self._cache_dirty = True
        self._tools_list: list[MCPTool] | None = None

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

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.cleanup()

    def invalidate_tools_cache(self):
        """Invalidate the tools cache."""
        self._cache_dirty = True

    async def connect(self):
        """Connect to the server."""
        try:
            transport = await self.exit_stack.enter_async_context(self.create_streams())
            read, write = transport
            session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await session.initialize()
            self.session = session
        except Exception as e:
            logger.error(f"Error initializing MCP server: {e}")
            await self.cleanup()
            raise

    async def list_tools(self) -> list[MCPTool]:
        """List the tools available on the server."""
        if not self.session:
            raise UserError(
                "Server not initialized. Make sure you call `connect()` first."
            )
        # Return from cache if caching is enabled, we have tools, and the cache is not dirty
        if self.cache_tools_list and not self._cache_dirty and self._tools_list:
            tools = self._tools_list
        else:
            # Reset the cache dirty to False
            self._cache_dirty = False
            # Fetch the tools from the server
            self._tools_list = (await self.session.list_tools()).tools
            tools = self._tools_list
        # Filter tools if allowed_tools is set
        if self.allowed_tools is not None:
            tools = [tool for tool in tools if getattr(tool, 'name', None) in self.allowed_tools]
        return tools

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any] | None
    ) -> CallToolResult:
        """Invoke a tool on the server."""
        if not self.session:
            raise UserError(
                "Server not initialized. Make sure you call `connect()` first."
            )

        return await self.session.call_tool(tool_name, arguments)

    async def cleanup(self):
        """Cleanup the server."""
        async with self._cleanup_lock:
            try:
                await self.exit_stack.aclose()
                self.session = None
            except Exception as e:
                logger.error(f"Error cleaning up server: {e}")


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
        """
        # For backwards compatibility, if strict is not provided, check if it's in the params
        if not strict:
            if "strict" in params:
                print("Strict parameter is deprecated. Use the strict argument instead.")
            strict = params.pop("strict", False)
        super().__init__(cache_tools_list, strict=strict, allowed_tools=allowed_tools)

        self.params = StdioServerParameters(
            command=params["command"],
            args=params.get("args", []),
            env=params.get("env"),
            cwd=params.get("cwd"),
            encoding=params.get("encoding", "utf-8"),
            encoding_error_handler=params.get("encoding_error_handler", "strict"),
        )

        self._name = name or f"stdio: {self.params.command}"

    def create_streams(
        self,
    ) -> AbstractAsyncContextManager[
        tuple[
            MemoryObjectReceiveStream[JSONRPCMessage | Exception],
            MemoryObjectSendStream[JSONRPCMessage],
        ]
    ]:
        """Create the streams for the server."""
        return stdio_client(self.params)

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
        """
        # For backwards compatibility, if strict is not provided, check if it's in the params
        if not strict:
            if "strict" in params:
                print("Strict parameter is deprecated. Use the strict argument instead.")
            strict = params.pop("strict", False)
        super().__init__(cache_tools_list, strict=strict, allowed_tools=allowed_tools)

        self.params = params
        self._name = name or f"sse: {self.params['url']}"

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

class MCPServerManager:
    """
    Thread-safe manager for persistent MCP server connections, enabling synchronous access to asynchronous MCP tools.

    MCPServerManager runs an MCP server in a dedicated background thread and asyncio event loop, allowing synchronous code to:
      - Connect and maintain a persistent MCP server session.
      - List available tools and call tools on the server from any thread.
      - Ensure all async context manager operations (connect, call_tool, cleanup) are performed in the same Task, preventing Python async context errors.
      - Cleanly shut down the server and release resources at application exit.
    """
    def __init__(self, mcp_server):
        self.mcp_server = mcp_server
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.queue = asyncio.Queue()
        self.shutdown_event = threading.Event()
        self.ready_event = threading.Event()
        self.thread.start()

    @property
    def name(self):
        return getattr(self.mcp_server, 'name', None)

    @property
    def strict(self):
        return getattr(self.mcp_server, 'strict', None)

    @property
    def params(self):
        return getattr(self.mcp_server, 'params', None)

    def __repr__(self):
        return f"<MCPServerManager name={self.name} strict={self.strict} params={self.params}>"

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._main())

    async def _main(self):
        await self.mcp_server.connect()
        self.ready_event.set()
        try:
            while True:
                item = await self.queue.get()
                if item == "SHUTDOWN":
                    break
                tool_name, args, result_future = item
                try:
                    result = await self.mcp_server.call_tool(tool_name, args)
                    result_future.set_result(result)
                except Exception as e:
                    result_future.set_exception(e)
        finally:
            await self.mcp_server.cleanup()
            self.shutdown_event.set()

    def call_tool(self, tool_name, args):
        self.ready_event.wait()
        result_future = Future()
        self.loop.call_soon_threadsafe(self.queue.put_nowait, (tool_name, args, result_future))
        return result_future.result()  # blocks until result is ready

    def shutdown(self):
        self.loop.call_soon_threadsafe(self.queue.put_nowait, "SHUTDOWN")
        self.shutdown_event.wait()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()

    def list_tools(self):
        self.ready_event.wait()
        coro = self.mcp_server.list_tools()
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()
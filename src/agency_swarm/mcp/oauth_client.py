"""OAuth-authenticated MCP client for Agency Swarm."""

import asyncio
import contextlib
import inspect
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, TypedDict, cast

import httpx
from agents import RunContextWrapper
from agents.agent import AgentBase
from agents.mcp.server import MCPServer
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamablehttp_client as _legacy_streamablehttp_client
from mcp.shared.message import SessionMessage
from mcp.types import (
    CallToolResult,
    GetPromptResult,
    ListPromptsResult,
    ReadResourceResult,
    Resource,
    Tool as MCPTool,
)
from pydantic import AnyUrl

from .oauth import (
    MCPServerOAuth,
    OAuthCallbackHandler,
    OAuthRedirectHandler,
    create_oauth_provider,
)

logger = logging.getLogger(__name__)


class OAuthHandlerMap(TypedDict, total=False):
    redirect: OAuthRedirectHandler
    callback: OAuthCallbackHandler


StreamableHTTPContext = AbstractAsyncContextManager[
    tuple[
        MemoryObjectReceiveStream[SessionMessage | Exception],
        MemoryObjectSendStream[SessionMessage],
        Callable[[], str | None],
    ]
]


def _get_modern_streamable_http_client() -> Callable[..., StreamableHTTPContext] | None:
    """Return modern streamable HTTP transport factory when available."""
    try:
        import mcp.client.streamable_http as streamable_http_module
    except ImportError:  # pragma: no cover - compatibility with older MCP SDKs
        return None
    modern_streamable_http_client = getattr(streamable_http_module, "streamable_http_client", None)
    if callable(modern_streamable_http_client):
        return cast("Callable[..., StreamableHTTPContext]", modern_streamable_http_client)
    return None


def _supports_keyword_argument(callable_obj: Callable[..., object], keyword: str) -> bool:
    """Return whether a transport factory accepts a keyword argument."""
    try:
        parameters = inspect.signature(callable_obj).parameters
    except (TypeError, ValueError):
        return False
    parameter = parameters.get(keyword)
    if parameter is not None and parameter.kind is not inspect.Parameter.POSITIONAL_ONLY:
        return True
    return any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())


def _build_streamable_transport(
    url: str,
    oauth_provider: OAuthClientProvider,
) -> tuple[StreamableHTTPContext, httpx.AsyncClient | None]:
    """Build streamable HTTP transport with auth across MCP SDK versions."""
    modern_streamable_http_client = _get_modern_streamable_http_client()
    if modern_streamable_http_client is not None:
        if _supports_keyword_argument(modern_streamable_http_client, "http_client"):
            http_client = httpx.AsyncClient(auth=oauth_provider, timeout=httpx.Timeout(30.0, read=300.0))
            return modern_streamable_http_client(url, http_client=http_client), http_client
        if _supports_keyword_argument(modern_streamable_http_client, "auth"):
            return modern_streamable_http_client(url, auth=oauth_provider), None
    return _legacy_streamablehttp_client(url, auth=oauth_provider), None


class MCPServerOAuthClient(MCPServer):
    """OAuth-authenticated MCP server client."""

    def __init__(
        self,
        oauth_config: MCPServerOAuth,
        custom_handlers: OAuthHandlerMap | None = None,
    ):
        """Initialize OAuth MCP client.

        Args:
            oauth_config: OAuth server configuration
            custom_handlers: Optional custom OAuth handlers dict with keys:
                - 'redirect': Custom redirect handler function
                - 'callback': Custom callback handler function
        """
        super().__init__(use_structured_content=False)
        self.oauth_config = oauth_config
        self._name = oauth_config.name
        self.session: ClientSession | None = None
        self._tools_list: list[MCPTool] | None = None
        self._oauth_provider: OAuthClientProvider | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._transport_context: StreamableHTTPContext | None = None
        self._transport_entered = False
        self._session_context: ClientSession | None = None
        self._session_entered = False

        # Track connection state
        self._authenticated = False

        # Extract custom handlers
        custom_handlers = custom_handlers or {}
        self._redirect_handler: OAuthRedirectHandler | None = custom_handlers.get("redirect")
        self._callback_handler: OAuthCallbackHandler | None = custom_handlers.get("callback")

        logger.info(f"Initialized OAuth MCP client for {self.name}")

    @property
    def name(self) -> str:
        """Return the MCP server name expected by the Agents SDK."""
        return self._name

    @property
    def cached_tools(self) -> list[MCPTool] | None:
        """Return the most recent OAuth-authenticated tool list, if fetched."""
        return self._tools_list

    async def connect(self) -> None:
        """Establish OAuth-authenticated connection to MCP server.

        The OAuth flow is handled by the MCP SDK's OAuthClientProvider:
        - Discovers OAuth endpoints
        - Handles authorization redirect
        - Exchanges code for tokens
        - Stores tokens for future use
        - Auto-refreshes tokens when expired

        Raises:
            Exception: If connection or OAuth flow fails
        """
        if self.session and self._authenticated:
            logger.debug(f"OAuth MCP client {self.name} already authenticated")
            return

        logger.info(f"Connecting with OAuth to: {self.name} at {self.oauth_config.url}")

        try:
            self._oauth_provider = await create_oauth_provider(
                self.oauth_config,
                redirect_handler=self._redirect_handler,
                callback_handler=self._callback_handler,
            )

            self._transport_context, self._http_client = _build_streamable_transport(
                self.oauth_config.url,
                self._oauth_provider,
            )
            read, write, _ = await self._transport_context.__aenter__()
            self._transport_entered = True

            self._session_context = ClientSession(read, write)
            self.session = await self._session_context.__aenter__()
            self._session_entered = True

            await self.session.initialize()
            self._authenticated = True
            logger.info(f"Successfully authenticated to OAuth MCP server: {self.name}")

        except asyncio.CancelledError:
            logger.info("OAuth MCP client connect cancelled: %s", self.name)
            # Ensure we close any partially-opened async context managers even when cancelled.
            await asyncio.shield(self.cleanup())
            raise
        except Exception:
            logger.exception(f"Failed to connect to OAuth MCP server: {self.name}")
            # Cleanup should not clobber the original error.
            with contextlib.suppress(Exception):
                await asyncio.shield(self.cleanup())
            raise

    async def list_tools(
        self,
        run_context: RunContextWrapper[object] | None = None,
        agent: AgentBase[Any] | None = None,
    ) -> list[MCPTool]:
        """List available tools from MCP server (OAuth required on HTTP transports).

        Args:
            run_context: Runner context (unused, kept for interface compatibility)
            agent: Agent requesting the list (unused, kept for interface compatibility)

        Returns:
            List of available tools from the MCP server

        Raises:
            Exception: If listing tools fails even with OAuth
        """
        await self.connect()
        assert self.session is not None
        logger.debug(f"Listing tools via authenticated session: {self.name}")
        result = await self.session.list_tools()
        logger.info(f"Found {len(result.tools)} tools from {self.name} (authenticated)")
        self._tools_list = list(result.tools)
        return self._tools_list

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> CallToolResult:
        """Call an OAuth MCP tool (requires authentication).

        This method ensures OAuth authentication is complete before calling.
        This is where OAuth is triggered - not during discovery/schema fetch.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            meta: Optional MCP request metadata

        Returns:
            Tool execution result

        Raises:
            Exception: If OAuth or tool call fails
        """
        # Tool calls ALWAYS require authenticated session
        if not self._authenticated:
            logger.info(f"Tool call requires OAuth, authenticating: {self.name}")
            await self.connect()
        assert self.session is not None

        logger.debug(f"Calling tool {tool_name} on OAuth MCP server: {self.name}")
        if meta is None:
            result = await self.session.call_tool(tool_name, arguments or {})
        else:
            result = await self.session.call_tool(tool_name, arguments or {}, meta=meta)
        logger.debug(f"Tool {tool_name} executed successfully on {self.name}")
        return result

    async def list_prompts(self) -> ListPromptsResult:
        """List available prompts from OAuth MCP server.

        Returns:
            Prompt list result from the MCP server

        Raises:
            Exception: If not connected or listing prompts fails
        """
        if not self.session:
            await self.connect()
        assert self.session is not None

        logger.debug(f"Listing prompts from OAuth MCP server: {self.name}")
        result = await self.session.list_prompts()
        return result

    async def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> GetPromptResult:
        """Get a prompt from OAuth MCP server.

        Args:
            name: Name of the prompt
            arguments: Prompt arguments

        Returns:
            Prompt result

        Raises:
            Exception: If not connected or getting prompt fails
        """
        if not self.session:
            await self.connect()
        assert self.session is not None

        logger.debug(f"Getting prompt {name} from OAuth MCP server: {self.name}")
        result = await self.session.get_prompt(name, arguments or {})
        return result

    async def list_resources(self) -> list[Resource]:
        """List available resources from OAuth MCP server.

        Returns:
            List of available resources from the MCP server

        Raises:
            Exception: If not connected or listing resources fails
        """
        if not self.session:
            await self.connect()
        assert self.session is not None

        logger.debug(f"Listing resources from OAuth MCP server: {self.name}")
        result = await self.session.list_resources()
        return result.resources

    async def read_resource(self, uri: str | AnyUrl) -> ReadResourceResult:
        """Read a resource from OAuth MCP server.

        Args:
            uri: Resource URI

        Returns:
            Resource content

        Raises:
            Exception: If not connected or reading resource fails
        """
        if not self.session:
            await self.connect()
        assert self.session is not None

        # Convert string to AnyUrl if needed
        uri_anyurl = AnyUrl(uri) if isinstance(uri, str) else uri

        logger.debug(f"Reading resource {uri} from OAuth MCP server: {self.name}")
        result = await self.session.read_resource(uri_anyurl)
        return result

    async def cleanup(self) -> None:
        """Cleanup OAuth MCP connection.

        Closes both discovery and authenticated sessions. Handles cross-task
        cleanup gracefully since connections may have been made from different tasks.
        """
        logger.info(f"Cleaning up OAuth MCP client: {self.name}")

        # Cleanup discovery session
        await self._cleanup_discovery()

        # Cleanup authenticated session
        if self._session_context and self._session_entered:
            try:
                await self._session_context.__aexit__(None, None, None)
            except RuntimeError as e:
                if "cancel scope" in str(e).lower() or "different task" in str(e).lower():
                    logger.debug(f"Session cleanup skipped (different task) for {self.name}")
                else:
                    logger.exception(f"Error closing session for {self.name}")
            except Exception:
                logger.exception(f"Error closing session for {self.name}")
            finally:
                self._session_entered = False

        self.session = None
        self._session_context = None
        self._authenticated = False

        if self._transport_context and self._transport_entered:
            try:
                await self._transport_context.__aexit__(None, None, None)
            except RuntimeError as e:
                if "cancel scope" in str(e).lower() or "different task" in str(e).lower():
                    logger.debug(f"Transport cleanup skipped (different task) for {self.name}")
                else:
                    logger.exception(f"Error closing transport for {self.name}")
            except Exception:
                logger.exception(f"Error closing transport for {self.name}")
            finally:
                self._transport_entered = False

        self._transport_context = None
        if self._http_client is not None:
            with contextlib.suppress(Exception):
                await self._http_client.aclose()
        self._http_client = None

        logger.info(f"Cleaned up OAuth MCP client: {self.name}")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """Async context manager exit."""
        await self.cleanup()

    async def _cleanup_discovery(self) -> None:
        """Retained for compatibility; discovery is not used for OAuth HTTP transports."""
        return None

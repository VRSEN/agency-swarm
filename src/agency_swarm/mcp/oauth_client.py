"""OAuth-authenticated MCP client for Agency Swarm.

This module provides the MCPServerOAuthClient class that wraps the MCP SDK's
OAuth client functionality, making it compatible with Agency Swarm's MCP integration.
"""

import logging
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pydantic import AnyUrl

from .oauth import MCPServerOAuth, create_oauth_provider

logger = logging.getLogger(__name__)


class MCPServerOAuthClient:
    """OAuth-authenticated MCP server client.

    This class wraps the MCP SDK's OAuth client to provide OAuth authentication
    for MCP servers. It follows the same interface as MCPServerStdio to work
    seamlessly with Agency Swarm's existing MCP integration.

    The OAuth flow happens automatically when connecting to the server:
    1. On first connection, if no tokens exist, the OAuth flow is triggered
    2. The user is prompted to authenticate via browser
    3. Tokens are cached locally for subsequent connections
    4. Token refresh happens automatically when needed

    Attributes:
        name: Unique identifier for this server (from oauth_config)
        oauth_config: Configuration for OAuth-enabled MCP server
        session: Active MCP client session (None until connected)
    """

    def __init__(
        self,
        oauth_config: MCPServerOAuth,
        custom_handlers: dict[str, Any] | None = None,
    ):
        """Initialize OAuth MCP client.

        Args:
            oauth_config: OAuth server configuration
            custom_handlers: Optional custom OAuth handlers dict with keys:
                - 'redirect': Custom redirect handler function
                - 'callback': Custom callback handler function
        """
        self.oauth_config = oauth_config
        self.name = oauth_config.name  # Required by mcp_manager
        self.session: ClientSession | None = None
        self._oauth_provider: Any = None
        self._transport_context: Any = None
        self._transport_entered = False
        self._session_context: ClientSession | None = None
        self._session_entered = False

        # Extract custom handlers
        custom_handlers = custom_handlers or {}
        self._redirect_handler = custom_handlers.get("redirect")
        self._callback_handler = custom_handlers.get("callback")

        logger.info(f"Initialized OAuth MCP client for {self.name}")

    async def connect(self) -> None:
        """Establish OAuth-authenticated connection to MCP server.

        This method:
        1. Creates an OAuth provider with token storage
        2. Connects to the MCP server using streamablehttp_client
        3. Initializes the MCP session
        4. Triggers OAuth flow if needed (on first 401 response)

        The OAuth flow is handled by the MCP SDK's OAuthClientProvider:
        - Discovers OAuth endpoints
        - Handles authorization redirect
        - Exchanges code for tokens
        - Stores tokens for future use
        - Auto-refreshes tokens when expired

        Raises:
            Exception: If connection or OAuth flow fails
        """
        if self.session:
            logger.debug(f"OAuth MCP client {self.name} already connected")
            return

        logger.info(f"Connecting to OAuth MCP server: {self.name} at {self.oauth_config.url}")

        try:
            self._oauth_provider = await create_oauth_provider(
                self.oauth_config,
                redirect_handler=self._redirect_handler,
                callback_handler=self._callback_handler,
            )

            self._transport_context = streamablehttp_client(self.oauth_config.url, auth=self._oauth_provider)
            read, write, _ = await self._transport_context.__aenter__()
            self._transport_entered = True

            self._session_context = ClientSession(read, write)
            self.session = await self._session_context.__aenter__()
            self._session_entered = True

            await self.session.initialize()
            logger.info(f"Successfully connected to OAuth MCP server: {self.name}")

        except Exception:
            logger.exception(f"Failed to connect to OAuth MCP server: {self.name}")
            await self.cleanup()
            raise

    async def list_tools(self) -> list[Any]:
        """List available tools from OAuth MCP server.

        Returns:
            List of available tools from the MCP server

        Raises:
            Exception: If not connected or listing tools fails
        """
        if not self.session:
            await self.connect()
        assert self.session is not None

        logger.debug(f"Listing tools from OAuth MCP server: {self.name}")
        result = await self.session.list_tools()
        logger.info(f"Found {len(result.tools)} tools from {self.name}")
        return result.tools

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Call an OAuth MCP tool.

        Args:
            name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool execution result

        Raises:
            Exception: If not connected or tool call fails
        """
        if not self.session:
            await self.connect()
        assert self.session is not None

        logger.debug(f"Calling tool {name} on OAuth MCP server: {self.name}")
        result = await self.session.call_tool(name, arguments or {})
        logger.debug(f"Tool {name} executed successfully on {self.name}")
        return result

    async def list_prompts(self) -> list[Any]:
        """List available prompts from OAuth MCP server.

        Returns:
            List of available prompts from the MCP server

        Raises:
            Exception: If not connected or listing prompts fails
        """
        if not self.session:
            await self.connect()
        assert self.session is not None

        logger.debug(f"Listing prompts from OAuth MCP server: {self.name}")
        result = await self.session.list_prompts()
        return result.prompts

    async def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
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

    async def list_resources(self) -> list[Any]:
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

    async def read_resource(self, uri: str | AnyUrl) -> Any:
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

        Closes the MCP session and transport context.
        """
        logger.info(f"Cleaning up OAuth MCP client: {self.name}")

        if self._session_context and self._session_entered:
            try:
                await self._session_context.__aexit__(None, None, None)
            except Exception:
                logger.exception(f"Error closing session for {self.name}")
            finally:
                self._session_entered = False

        self.session = None
        self._session_context = None

        if self._transport_context and self._transport_entered:
            try:
                await self._transport_context.__aexit__(None, None, None)
            except Exception:
                logger.exception(f"Error closing transport for {self.name}")
            finally:
                self._transport_entered = False

        self._transport_context = None

        logger.info(f"Cleaned up OAuth MCP client: {self.name}")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """Async context manager exit."""
        await self.cleanup()

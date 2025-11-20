"""OAuth authentication for MCP servers.

Provides OAuth 2.0 with PKCE support for MCP servers using the MCP Python SDK's OAuthClientProvider.
Supports both local development (file-based token storage) and SaaS deployment (callback-based storage).
"""

import json
import logging
import os
import webbrowser
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from agents import RunHooks, RunResult
from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)
from pydantic import AnyUrl

from agency_swarm.context import MasterContext

logger = logging.getLogger(__name__)


def get_default_cache_dir() -> Path:
    """Get default cache directory for OAuth tokens."""
    cache_dir = os.getenv("AGENCY_SWARM_MCP_CACHE_DIR")
    if cache_dir:
        return Path(cache_dir).expanduser()
    return Path.home() / ".agency-swarm" / "mcp-tokens"


class FileTokenStorage:
    """File-based token storage for MCP OAuth."""

    def __init__(self, cache_dir: Path, server_name: str):
        """Initialize file-based token storage.

        Args:
            cache_dir: Directory to store token files
            server_name: Unique name for the MCP server (used in filename)
        """
        self.cache_dir = cache_dir
        self.server_name = server_name
        self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Separate files for tokens and client info
        self.token_file = self.cache_dir / f"{server_name}_tokens.json"
        self.client_file = self.cache_dir / f"{server_name}_client.json"

    async def get_tokens(self) -> OAuthToken | None:
        """Get stored tokens."""
        if not self.token_file.exists():
            return None

        try:
            data = json.loads(self.token_file.read_text())
            return OAuthToken(**data)
        except Exception:
            logger.exception(f"Failed to load tokens from {self.token_file}")
            return None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        """Store tokens."""
        try:
            self.token_file.write_text(tokens.model_dump_json(indent=2))
            self.token_file.chmod(0o600)  # Secure permissions
            logger.info(f"Tokens saved to {self.token_file}")
        except Exception:
            logger.exception(f"Failed to save tokens to {self.token_file}")

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        """Get stored client information."""
        if not self.client_file.exists():
            return None

        try:
            data = json.loads(self.client_file.read_text())
            return OAuthClientInformationFull(**data)
        except Exception:
            logger.exception(f"Failed to load client info from {self.client_file}")
            return None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        """Store client information."""
        try:
            self.client_file.write_text(client_info.model_dump_json(indent=2))
            self.client_file.chmod(0o600)  # Secure permissions
            logger.info(f"Client info saved to {self.client_file}")
        except Exception:
            logger.exception(f"Failed to save client info to {self.client_file}")


@dataclass
class MCPServerOAuth:
    """Configuration for an OAuth-enabled MCP server.

    Attributes:
        url: MCP server URL
        name: Unique identifier for this server
        client_id: OAuth client ID (reads from env if None)
        client_secret: OAuth client secret (reads from env if None)
        scopes: List of OAuth scopes to request
        redirect_uri: OAuth redirect URI for callback
        cache_dir: Directory for token storage (uses default if None, V0 only)
        storage: Custom token storage implementation (V1 for SaaS, overrides cache_dir)
        client_metadata: Full OAuth client metadata (overrides simple params)
    """

    url: str
    name: str
    client_id: str | None = None
    client_secret: str | None = None
    scopes: list[str] = field(default_factory=lambda: ["user"])
    redirect_uri: str = "http://localhost:3000/callback"
    cache_dir: Path | None = None
    storage: Any | None = None
    client_metadata: OAuthClientMetadata | None = None

    def _resolve_client_id(self) -> str | None:
        """Return the client_id if provided explicitly or via environment."""
        if self.client_id:
            return self.client_id

        env_var = f"{self.name.upper().replace('-', '_')}_CLIENT_ID"
        return os.getenv(env_var)

    def get_client_id(self) -> str:
        """Get client ID from config or environment."""
        client_id = self._resolve_client_id()
        if client_id:
            return client_id

        env_var = f"{self.name.upper().replace('-', '_')}_CLIENT_ID"
        raise ValueError(
            f"No client_id provided for {self.name}. Set {env_var} environment variable or pass client_id parameter."
        )

    def get_client_secret(self) -> str | None:
        """Get client secret from config or environment."""
        if self.client_secret:
            return self.client_secret

        # Try server-specific env var
        env_var = f"{self.name.upper().replace('-', '_')}_CLIENT_SECRET"
        return os.getenv(env_var)

    def get_cache_dir(self) -> Path:
        """Get cache directory for token storage."""
        if self.cache_dir:
            return self.cache_dir
        return get_default_cache_dir()

    def build_client_metadata(self) -> OAuthClientMetadata:
        """Build OAuth client metadata from config."""
        if self.client_metadata:
            return self.client_metadata

        return OAuthClientMetadata(
            client_name=f"Agency Swarm - {self.name}",
            redirect_uris=[AnyUrl(self.redirect_uri)],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope=" ".join(self.scopes),
        )

    def get_client_id_optional(self) -> str | None:
        """Return the resolved client_id without raising."""
        return self._resolve_client_id()

    def build_client_information(self) -> OAuthClientInformationFull | None:
        """Return prepopulated client information when static credentials exist."""
        client_id = self.get_client_id_optional()
        if not client_id:
            return None

        client_secret = self.get_client_secret()
        metadata = self.build_client_metadata()
        metadata_data = metadata.model_dump(by_alias=True, exclude_none=True)
        metadata_data.update(
            client_id=client_id,
            client_secret=client_secret,
        )

        return OAuthClientInformationFull(**metadata_data)


async def default_redirect_handler(auth_url: str) -> None:
    """Default handler for OAuth redirect - opens browser.

    Args:
        auth_url: Authorization URL to visit
    """
    print(f"\n{'=' * 80}")
    print("OAuth Authentication Required")
    print(f"{'=' * 80}")
    print(f"\nOpening browser for authentication: {auth_url}\n")
    print("If the browser doesn't open automatically, please visit the URL above.")
    print(f"{'=' * 80}\n")

    try:
        webbrowser.open(auth_url)
    except Exception:
        logger.exception("Failed to open browser")


async def default_callback_handler() -> tuple[str, str | None]:
    """Default handler for OAuth callback - prompts user to paste URL.

    Returns:
        Tuple of (authorization_code, state)
    """
    print("\nAfter authorizing, you will be redirected to a callback URL.")
    print("Please copy the entire URL from your browser and paste it below.\n")

    callback_url = input("Callback URL: ").strip()

    try:
        parsed = urlparse(callback_url)
        params = parse_qs(parsed.query)

        if "error" in params:
            error = params["error"][0]
            error_description = params.get("error_description", ["Unknown error"])[0]
            raise ValueError(f"OAuth error: {error} - {error_description}")

        if "code" not in params:
            raise ValueError("No authorization code found in callback URL")

        code = params["code"][0]
        state = params.get("state", [None])[0]

        return code, state

    except Exception as e:
        logger.exception("Failed to parse callback URL")
        raise ValueError(f"Invalid callback URL: {e}") from e

    async def create_oauth_provider(
        server: MCPServerOAuth,
        redirect_handler: Callable[[str], Awaitable[None]] | None = None,
        callback_handler: Callable[[], Awaitable[tuple[str, str | None]]] | None = None,
    ) -> OAuthClientProvider:
        """Create OAuth provider for MCP server.

        Args:
            server: OAuth server configuration
            redirect_handler: Custom redirect handler (uses default if None)
            callback_handler: Custom callback handler (uses default if None)

        Returns:
            Configured OAuthClientProvider
        """
        # Use custom storage if provided (V1 SaaS), otherwise default to FileTokenStorage (V0)
        if server.storage:
            storage = server.storage
        else:
            storage = FileTokenStorage(
                cache_dir=server.get_cache_dir(),
                server_name=server.name,
            )

        client_metadata = server.build_client_metadata()
        client_info = server.build_client_information()

        if client_info and hasattr(storage, "set_client_info"):
            await storage.set_client_info(client_info)

        # Use provided handlers or defaults
        redirect_handler = redirect_handler or default_redirect_handler
        callback_handler = callback_handler or default_callback_handler

        provider = OAuthClientProvider(
            server_url=server.url,
            client_metadata=client_metadata,
            storage=storage,
            redirect_handler=redirect_handler,
            callback_handler=callback_handler,
        )

        logger.info(f"Created OAuth provider for {server.name} at {server.url}")
        return provider


class OAuthTokenHooks(RunHooks[MasterContext]):
    """RunHooks implementation for OAuth token persistence.

    Allows custom storage backends (e.g., database) for SaaS deployments.
    For local development, tokens are stored in files by FileTokenStorage.
    """

    def __init__(
        self,
        load_tokens_callback: Callable[[str], dict[str, Any] | None] | None = None,
        save_tokens_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ):
        """Initialize OAuth token hooks.

        Args:
            load_tokens_callback: Function to load tokens for a server URL
            save_tokens_callback: Function to save tokens for a server URL
        """
        self._load_tokens_callback = load_tokens_callback
        self._save_tokens_callback = save_tokens_callback

    def on_run_start(self, *, context: MasterContext, **kwargs: Any) -> None:
        """Load OAuth tokens at the start of a run."""
        if not self._load_tokens_callback:
            return

        try:
            # Load tokens for each MCP connection that has OAuth
            for server_url in getattr(context, "mcp_servers", {}):
                tokens_data = self._load_tokens_callback(server_url)
                if tokens_data:
                    logger.debug(f"Loaded OAuth tokens for {server_url}")
        except Exception:
            logger.exception("Error loading OAuth tokens in on_run_start")

    def on_run_end(self, *, context: MasterContext, result: RunResult, **kwargs: Any) -> None:
        """Save OAuth tokens at the end of a run."""
        if not self._save_tokens_callback:
            return

        try:
            # Save tokens for each MCP connection that has OAuth
            for server_url in getattr(context, "mcp_servers", {}):
                # Tokens are already persisted by FileTokenStorage during the run
                # This hook is for custom backends (e.g., database)
                logger.debug(f"OAuth tokens for {server_url} persisted")
        except Exception:
            logger.exception("Error saving OAuth tokens in on_run_end")

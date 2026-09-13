"""Configuration model for OAuth-enabled MCP servers."""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlsplit

from mcp.client.auth.oauth2 import TokenStorage
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
)
from pydantic import AnyUrl

from .oauth import (
    OAuthCallbackHandler,
    OAuthRedirectHandler,
    get_default_cache_dir,
)
from .oauth_provider import preserve_configured_scopes
from .oauth_user import build_oauth_cache_segment


@dataclass(eq=False)
class MCPServerOAuth:
    """Configuration for an OAuth-enabled MCP server.

    Attributes:
        url: MCP server URL
        name: Unique identifier for this server
        client_id: OAuth client ID (reads from env if None and use_env_credentials=True)
        client_secret: OAuth client secret (reads from env if None and use_env_credentials=True)
        scopes: OAuth scopes to request. When omitted, discovery supplies the default.
        redirect_uri: OAuth redirect URI for callback
        cache_dir: Directory for token storage (uses default if None)
        storage: Custom token storage implementation (overrides cache_dir)
        storage_factory: Factory function to create storage per-request (for multi-tenant)
        client_metadata: Full OAuth client metadata (overrides simple params)
        auth_server_url: Base URL for OAuth discovery when different from MCP endpoint
        use_env_credentials: If False, don't read client_id/secret from environment.
            Set to False for self-hosted servers using Dynamic Client Registration (DCR).
        redirect_handler: Custom handler for OAuth redirect (opens browser by default)
        callback_handler: Custom handler to receive OAuth callback code
    """

    DEFAULT_REDIRECT_URI: ClassVar[str] = "http://localhost:8000/auth/callback"

    url: str
    name: str
    client_id: str | None = None
    client_secret: str | None = None
    scopes: list[str] | None = None
    redirect_uri: str | None = None
    cache_dir: Path | None = None
    storage: TokenStorage | None = None
    storage_factory: Callable[[str, str], TokenStorage] | None = None
    client_metadata: OAuthClientMetadata | None = None
    auth_server_url: str | None = None
    use_env_credentials: bool = True
    redirect_handler: OAuthRedirectHandler | None = None
    callback_handler: OAuthCallbackHandler | None = None

    def _resolve_client_id(self) -> str | None:
        """Return the client_id if provided explicitly or via environment."""
        if self.client_id:
            return self.client_id

        if not self.use_env_credentials:
            return None

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

        if not self.use_env_credentials:
            return None

        # Try server-specific env var
        env_var = f"{self.name.upper().replace('-', '_')}_CLIENT_SECRET"
        return os.getenv(env_var)

    def get_cache_dir(self) -> Path:
        """Get cache directory for token storage."""
        if self.cache_dir:
            return self.cache_dir
        return get_default_cache_dir()

    def build_client_metadata(self) -> OAuthClientMetadata:
        """Build effective OAuth client metadata from config."""
        if self.client_metadata:
            metadata = self.client_metadata.model_copy(deep=True)
        else:
            metadata = OAuthClientMetadata(
                client_name=f"Agency Swarm - {self.name}",
                redirect_uris=[AnyUrl(self.get_redirect_uri())],
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
                scope=" ".join(self.scopes) if self.scopes is not None else None,
            )

        if self.get_client_secret() and metadata.token_endpoint_auth_method is None:
            metadata = metadata.model_copy(update={"token_endpoint_auth_method": "client_secret_basic"})
        return preserve_configured_scopes(metadata, self.scopes)

    def get_client_id_optional(self) -> str | None:
        """Return the resolved client_id without raising."""
        return self._resolve_client_id()

    def get_redirect_uri(self) -> str:
        """Resolve redirect URI with explicit > server env > global env > default."""
        if self.redirect_uri:
            return self.redirect_uri
        server_env = f"{self.name.upper().replace('-', '_')}_REDIRECT_URI"
        if os.getenv(server_env):
            return os.getenv(server_env, self.DEFAULT_REDIRECT_URI)
        if os.getenv("OAUTH_CALLBACK_URL"):
            return os.getenv("OAUTH_CALLBACK_URL", self.DEFAULT_REDIRECT_URI)
        return self.DEFAULT_REDIRECT_URI

    def get_callback_redirect_uri(self, client_metadata: OAuthClientMetadata) -> str:
        """Return the advertised URI used by the default local callback listener."""
        if client_metadata.redirect_uris:
            return str(client_metadata.redirect_uris[0])
        return self.get_redirect_uri()

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

    def get_client_identity(self) -> str:
        """Return a stable, secret-free identity for OAuth persistence."""
        metadata = self.build_client_metadata()
        identity = json.dumps(
            {
                "auth_server_url": self.get_auth_server_url(),
                "client_id": self.get_client_id_optional(),
                "client_metadata": metadata.model_dump(mode="json", by_alias=True, exclude_none=True),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return build_oauth_cache_segment(identity, max_prefix_length=48)

    def get_auth_server_url(self) -> str | None:
        """Return the OAuth authorization server base URL."""
        if self.auth_server_url:
            return self.auth_server_url

        parsed = urlsplit(self.url)
        if not parsed.scheme or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}"

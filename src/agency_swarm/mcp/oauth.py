"""OAuth authentication for MCP servers.

Provides OAuth 2.0 with PKCE support for MCP servers using the MCP Python SDK's OAuthClientProvider.
Supports unified local/SaaS token storage via contextvars.
"""

import asyncio
import contextlib
import json
import logging
import os
import webbrowser
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Literal, TypedDict, cast
from urllib.parse import parse_qs, urlparse, urlsplit

from mcp.client.auth import OAuthClientProvider
from mcp.client.auth.oauth2 import TokenStorage
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)
from pydantic import AnyUrl

# Contextvar for per-user token isolation
_user_id_context: ContextVar[str | None] = ContextVar("oauth_user_id", default=None)


def set_oauth_user_id(user_id: str | None) -> None:
    """Set the current user ID for OAuth token isolation.

    This must be called before MCP server connections are established
    to ensure tokens are stored in the correct per-user directory.

    Args:
        user_id: The user ID to associate with OAuth tokens, or None for default.
    """
    _user_id_context.set(user_id)
    logger.debug(f"OAuth user_id context set to: {user_id}")


class TokenPayload(TypedDict, total=False):
    access_token: str
    token_type: Literal["Bearer"]
    expires_in: int | None
    scope: str | None
    refresh_token: str | None


OAuthRedirectHandler = Callable[[str], Awaitable[None]]
OAuthCallbackHandler = Callable[[], Awaitable[tuple[str, str | None]]]


@dataclass
class TokenCallbackRegistry:
    """Holds optional load/save callbacks for token persistence."""

    load_callback: Callable[[str], TokenPayload | None] | None = None
    save_callback: Callable[[str, TokenPayload], None] | None = None

    def has_callbacks(self) -> bool:
        """Return True if any callback has been configured."""
        return self.load_callback is not None or self.save_callback is not None


_TOKEN_CALLBACK_REGISTRY = TokenCallbackRegistry()

logger = logging.getLogger(__name__)


def get_default_cache_dir() -> Path:
    """Get default cache directory for OAuth tokens."""
    cache_dir = os.getenv("AGENCY_SWARM_MCP_CACHE_DIR")
    if cache_dir:
        return Path(cache_dir).expanduser()
    return Path.home() / ".agency-swarm" / "mcp-tokens"


class FileTokenStorage:
    """File-based token storage for MCP OAuth with per-user isolation."""

    def __init__(
        self,
        cache_dir: Path,
        server_name: str,
        server_url: str | None = None,
        token_callbacks: TokenCallbackRegistry | None = None,
    ):
        """Initialize file-based token storage.

        Args:
            cache_dir: Base directory for token storage
            server_name: Unique name for the MCP server (used in filename)
            server_url: Full MCP endpoint URL (used for callback identification)
            token_callbacks: Optional callback registry for custom persistence
        """
        self.base_cache_dir = cache_dir
        self.server_name = server_name
        self.server_url = server_url or server_name
        self._token_callbacks = token_callbacks

    def _get_user_cache_dir(self) -> Path:
        """Get cache directory for current user from contextvar."""
        user_id = _user_id_context.get()
        if user_id:
            user_dir = self.base_cache_dir / user_id
        else:
            user_dir = self.base_cache_dir / "default"
        user_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        return user_dir

    def _get_server_cache_dir(self) -> Path:
        """Get cache directory for current server under the current user."""
        server_dir = self._get_user_cache_dir() / self.server_name
        server_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        return server_dir

    def _legacy_token_file(self) -> Path:
        """Return legacy flat token file path for migration."""
        return self._get_user_cache_dir() / f"{self.server_name}_tokens.json"

    def _legacy_client_file(self) -> Path:
        """Return legacy flat client file path for migration."""
        return self._get_user_cache_dir() / f"{self.server_name}_client.json"

    async def get_tokens(self) -> OAuthToken | None:
        """Get stored tokens for current user."""
        if self._token_callbacks and self._token_callbacks.load_callback:
            try:
                data = self._token_callbacks.load_callback(self.server_url)
                if data:
                    return OAuthToken(**data)
            except Exception:
                logger.exception("OAuth load_tokens_callback failed")

        server_dir = self._get_server_cache_dir()
        token_file = server_dir / "tokens.json"

        if not token_file.exists():
            legacy_file = self._legacy_token_file()
            if not legacy_file.exists():
                return None
            try:
                data = cast("TokenPayload", json.loads(legacy_file.read_text()))
                tokens = OAuthToken(**data)
                token_file.write_text(tokens.model_dump_json(indent=2))
                token_file.chmod(0o600)
                with contextlib.suppress(FileNotFoundError):
                    legacy_file.unlink()
                logger.info("Migrated legacy OAuth tokens to server-specific directory")
                return tokens
            except Exception:
                logger.exception(f"Failed to migrate tokens from {legacy_file}")
                return None

        try:
            data = cast("TokenPayload", json.loads(token_file.read_text()))
            return OAuthToken(**data)
        except Exception:
            logger.exception(f"Failed to load tokens from {token_file}")
            return None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        """Store tokens for current user."""
        server_dir = self._get_server_cache_dir()
        token_file = server_dir / "tokens.json"

        try:
            token_file.write_text(tokens.model_dump_json(indent=2))
            token_file.chmod(0o600)  # Secure permissions
            logger.info(f"Tokens saved to {token_file}")
            # Clean up legacy flat file if it exists
            legacy_file = self._legacy_token_file()
            with contextlib.suppress(FileNotFoundError):
                legacy_file.unlink()
        except Exception:
            logger.exception(f"Failed to save tokens to {token_file}")
        if self._token_callbacks and self._token_callbacks.save_callback:
            try:
                payload = cast("TokenPayload", tokens.model_dump())
                self._token_callbacks.save_callback(self.server_url, payload)
            except Exception:
                logger.exception("OAuth save_tokens_callback failed")

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        """Get stored client information for current user."""
        server_dir = self._get_server_cache_dir()
        client_file = server_dir / "client.json"

        if not client_file.exists():
            legacy_file = self._legacy_client_file()
            if not legacy_file.exists():
                return None
            try:
                data = json.loads(legacy_file.read_text())
                client_info = OAuthClientInformationFull(**data)
                client_file.write_text(client_info.model_dump_json(indent=2))
                client_file.chmod(0o600)
                with contextlib.suppress(FileNotFoundError):
                    legacy_file.unlink()
                logger.info("Migrated legacy OAuth client info to server-specific directory")
                return client_info
            except Exception:
                logger.exception(f"Failed to migrate client info from {legacy_file}")
                return None

        try:
            data = json.loads(client_file.read_text())
            return OAuthClientInformationFull(**data)
        except Exception:
            logger.exception(f"Failed to load client info from {client_file}")
            return None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        """Store client information for current user."""
        server_dir = self._get_server_cache_dir()
        client_file = server_dir / "client.json"

        try:
            client_file.write_text(client_info.model_dump_json(indent=2))
            client_file.chmod(0o600)  # Secure permissions
            logger.info(f"Client info saved to {client_file}")
            legacy_file = self._legacy_client_file()
            with contextlib.suppress(FileNotFoundError):
                legacy_file.unlink()
        except Exception:
            logger.exception(f"Failed to save client info to {client_file}")


@dataclass(eq=False)
class MCPServerOAuth:
    """Configuration for an OAuth-enabled MCP server.

    Attributes:
        url: MCP server URL
        name: Unique identifier for this server
        client_id: OAuth client ID (reads from env if None and use_env_credentials=True)
        client_secret: OAuth client secret (reads from env if None and use_env_credentials=True)
        scopes: List of OAuth scopes to request
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
    scopes: list[str] = field(default_factory=lambda: ["user"])
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
        """Build OAuth client metadata from config."""
        if self.client_metadata:
            return self.client_metadata

        redirect_uri = self.get_redirect_uri()
        return OAuthClientMetadata(
            client_name=f"Agency Swarm - {self.name}",
            redirect_uris=[AnyUrl(redirect_uri)],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope=" ".join(self.scopes),
        )

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

    def get_auth_server_url(self) -> str | None:
        """Return the OAuth authorization server base URL."""
        if self.auth_server_url:
            return self.auth_server_url

        parsed = urlsplit(self.url)
        if not parsed.scheme or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}"


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
    print("The terminal will automatically capture the callback or you can paste it manually.")
    print(f"{'=' * 80}\n")

    try:
        webbrowser.open(auth_url)
    except Exception:
        logger.exception("Failed to open browser")


def _parse_callback_response(callback_url: str) -> tuple[str, str | None]:
    """Parse authorization code and state from a callback URL."""
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


async def _prompt_for_callback_url() -> tuple[str, str | None]:
    """Prompt the user to paste the callback URL."""
    print("\nAfter authorizing, you will be redirected to a callback URL.")
    print("Paste the full URL here if automatic capture does not complete.\n")

    loop = asyncio.get_event_loop()
    callback_url = await loop.run_in_executor(None, lambda: input("Callback URL: ").strip())
    return _parse_callback_response(callback_url)


def _can_use_local_callback_server(redirect_uri: str) -> bool:
    """Return True if we can bind a local HTTP server for the redirect URI."""
    parsed = urlparse(redirect_uri)
    if parsed.scheme != "http":
        return False

    host = parsed.hostname or ""
    return host in {"localhost", "127.0.0.1"}


async def _listen_for_callback_once(redirect_uri: str, timeout: float = 300.0) -> tuple[str, str | None]:
    """Start a local HTTP server and capture the first callback request."""
    parsed = urlparse(redirect_uri)
    host = parsed.hostname or "localhost"
    port = parsed.port or 80
    path = parsed.path or "/auth/callback"
    loop = asyncio.get_event_loop()
    result: asyncio.Future[tuple[str, str | None]] = loop.create_future()

    async def _handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            data = await reader.readuntil(b"\r\n\r\n")
        except asyncio.IncompleteReadError:
            writer.close()
            await writer.wait_closed()
            return

        request_line = data.split(b"\r\n", 1)[0].decode(errors="ignore")
        parts = request_line.split(" ")
        target = parts[1] if len(parts) >= 2 else ""
        target_parsed = urlparse(target)
        # Some browsers send absolute URLs, others only the path.
        request_path = target_parsed.path or target

        status_line = "HTTP/1.1 200 OK\r\n"
        body = (
            "<html><body>"
            "<h1>You may close this tab.</h1>"
            "<p>Return to Agency Swarm. The terminal captured your authorization code.</p>"
            "</body></html>"
        )

        try:
            if request_path != path:
                status_line = "HTTP/1.1 404 Not Found\r\n"
                body = "<html><body><h1>404 Not Found</h1></body></html>"
                writer.write(
                    f"{status_line}Content-Type: text/html\r\nContent-Length: {len(body)}\r\n\r\n{body}".encode()
                )
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            params = parse_qs(target_parsed.query)

            # Handle OAuth provider error responses (e.g., user denied authorization)
            if "error" in params:
                error = params["error"][0]
                error_description = params.get("error_description", ["Unknown error"])[0]
                status_line = "HTTP/1.1 400 Bad Request\r\n"
                body = f"<html><body><h1>OAuth Error</h1><p>{error}: {error_description}</p></body></html>"
                writer.write(
                    f"{status_line}Content-Type: text/html\r\nContent-Length: {len(body)}\r\n\r\n{body}".encode()
                )
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                if not result.done():
                    result.set_exception(ValueError(f"OAuth error: {error} - {error_description}"))
                return

            if "code" not in params:
                status_line = "HTTP/1.1 400 Bad Request\r\n"
                body = "<html><body><h1>Missing code parameter.</h1></body></html>"
                writer.write(
                    f"{status_line}Content-Type: text/html\r\nContent-Length: {len(body)}\r\n\r\n{body}".encode()
                )
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            if not result.done():
                code = params["code"][0]
                state = params.get("state", [None])[0]
                result.set_result((code, state))

            writer.write(f"{status_line}Content-Type: text/html\r\nContent-Length: {len(body)}\r\n\r\n{body}".encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(_handle_connection, host=host, port=port)
    print(f"\nListening for OAuth callback at {redirect_uri}\n")

    try:
        return await asyncio.wait_for(result, timeout=timeout)
    finally:
        server.close()
        await server.wait_closed()


async def default_callback_handler(redirect_uri: str | None = None) -> tuple[str, str | None]:
    """Default handler for OAuth callback.

    Tries to capture the callback automatically using a local HTTP server and falls
    back to a manual prompt when automatic capture is not possible.

    Returns:
        Tuple of (authorization_code, state)
    """
    redirect_target = redirect_uri or "http://localhost:8000/auth/callback"
    tasks: list[asyncio.Task[tuple[str, str | None]]] = []
    server_task: asyncio.Task[tuple[str, str | None]] | None = None

    if _can_use_local_callback_server(redirect_target):
        try:
            server_task = asyncio.create_task(_listen_for_callback_once(redirect_target))
            tasks.append(server_task)
        except OSError:
            logger.warning("Local callback server unavailable; falling back to manual entry.")

    prompt_task = asyncio.create_task(_prompt_for_callback_url())
    tasks.append(prompt_task)

    pending: set[asyncio.Task[tuple[str, str | None]]] = set(tasks)

    try:
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for finished in done:
                try:
                    result = finished.result()
                except EOFError as exc:
                    # Non-interactive environments (e.g. background workers) cannot
                    # satisfy the fallback stdin prompt.
                    raise RuntimeError(
                        "OAuth callback input is unavailable in non-interactive mode. "
                        "Use FastAPI OAuth handlers or provide a callback URL."
                    ) from exc
                except OSError as exc:
                    if server_task is not None and finished is server_task:
                        logger.warning("Local callback server failed (%s); falling back to manual entry.", exc)
                        continue
                    logger.exception("OAuth callback handler error")
                    raise
                except Exception:
                    logger.exception("OAuth callback handler error")
                    raise
                else:
                    return result
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    raise RuntimeError("OAuth callback failed: no tasks completed successfully")


async def create_oauth_provider(
    server: MCPServerOAuth,
    redirect_handler: OAuthRedirectHandler | None = None,
    callback_handler: OAuthCallbackHandler | None = None,
) -> OAuthClientProvider:
    """Create OAuth provider for MCP server.

    Args:
        server: OAuth server configuration
        redirect_handler: Custom redirect handler (uses default if None)
        callback_handler: Custom callback handler (uses default if None)

    Returns:
        Configured OAuthClientProvider
    """
    # Prioritize storage creation: storage_factory > storage > FileTokenStorage
    if server.storage_factory:
        storage = server.storage_factory(server.name, server.url)
    elif server.storage:
        storage = server.storage
    else:
        storage = FileTokenStorage(
            cache_dir=server.get_cache_dir(),
            server_name=server.name,
            server_url=server.url,
            token_callbacks=_TOKEN_CALLBACK_REGISTRY,
        )

    client_metadata = server.build_client_metadata()
    client_info = server.build_client_information()

    if client_info and hasattr(storage, "set_client_info"):
        await storage.set_client_info(client_info)

    # Handler precedence: explicit args > server-level handlers > defaults
    redirect_handler = redirect_handler or server.redirect_handler or default_redirect_handler
    if callback_handler is None:
        callback_handler = server.callback_handler
    if callback_handler is None:

        async def _wrapped_callback_handler() -> tuple[str, str | None]:
            return await default_callback_handler(server.get_redirect_uri())

        callback_handler = _wrapped_callback_handler

    provider = OAuthClientProvider(
        server_url=server.url,
        client_metadata=client_metadata,
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )

    auth_base_url = server.get_auth_server_url()
    if auth_base_url:
        provider.context.auth_server_url = auth_base_url

    logger.info(f"Created OAuth provider for {server.name} at {server.url}")
    return provider

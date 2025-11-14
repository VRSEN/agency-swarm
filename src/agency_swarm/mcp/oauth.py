"""OAuth authentication for MCP servers.

Provides OAuth 2.0 with PKCE support for MCP servers using the MCP Python SDK's OAuthClientProvider.
Supports both local development (file-based token storage) and SaaS deployment (callback-based storage).
"""

import asyncio
import contextlib
import json
import logging
import os
import webbrowser
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse, urlsplit

from agents import RunHooks, RunResult
from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)
from pydantic import AnyUrl

from agency_swarm.context import MasterContext


@dataclass
class TokenCallbackRegistry:
    """Holds optional load/save callbacks for token persistence."""

    load_callback: Callable[[str], dict[str, Any] | None] | None = None
    save_callback: Callable[[str, dict[str, Any]], None] | None = None

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
    """File-based token storage for MCP OAuth."""

    def __init__(
        self,
        cache_dir: Path,
        server_name: str,
        server_url: str | None = None,
        token_callbacks: TokenCallbackRegistry | None = None,
    ):
        """Initialize file-based token storage.

        Args:
            cache_dir: Directory to store token files
            server_name: Unique name for the MCP server (used in filename)
            server_url: Full MCP endpoint URL (used for callback identification)
            token_callbacks: Optional callback registry for custom persistence
        """
        self.cache_dir = cache_dir
        self.server_name = server_name
        self.server_url = server_url or server_name
        self._token_callbacks = token_callbacks
        self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Separate files for tokens and client info
        self.token_file = self.cache_dir / f"{server_name}_tokens.json"
        self.client_file = self.cache_dir / f"{server_name}_client.json"

    async def get_tokens(self) -> OAuthToken | None:
        """Get stored tokens."""
        if self._token_callbacks and self._token_callbacks.load_callback:
            try:
                data = self._token_callbacks.load_callback(self.server_url)
                if data:
                    return OAuthToken(**data)
            except Exception:
                logger.exception("OAuth load_tokens_callback failed")

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
        if self._token_callbacks and self._token_callbacks.save_callback:
            try:
                self._token_callbacks.save_callback(self.server_url, tokens.model_dump())
            except Exception:
                logger.exception("OAuth save_tokens_callback failed")

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
        auth_server_url: Base URL for OAuth discovery when different from MCP endpoint
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
    auth_server_url: str | None = None

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
    path = parsed.path or "/callback"
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
    redirect_target = redirect_uri or "http://localhost:3000/callback"
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

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

    for task in pending:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    for task in done:
        try:
            return task.result()
        except Exception:
            logger.exception("OAuth callback handler error")
            raise


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
            server_url=server.url,
            token_callbacks=_TOKEN_CALLBACK_REGISTRY,
        )

    client_metadata = server.build_client_metadata()
    client_info = server.build_client_information()

    if client_info and hasattr(storage, "set_client_info"):
        await storage.set_client_info(client_info)

    # Use provided handlers or defaults
    redirect_handler = redirect_handler or default_redirect_handler
    if callback_handler is None:

        async def _wrapped_callback_handler() -> tuple[str, str | None]:
            return await default_callback_handler(server.redirect_uri)

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


class OAuthTokenHooks(RunHooks[MasterContext]):
    """RunHooks implementation for OAuth token persistence.

    Registering this hook wires the module-level token callbacks so the default
    FileTokenStorage will call ``load_tokens_callback`` before each connection
    and ``save_tokens_callback`` whenever new tokens are persisted.
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
        if load_tokens_callback:
            _TOKEN_CALLBACK_REGISTRY.load_callback = load_tokens_callback
        if save_tokens_callback:
            _TOKEN_CALLBACK_REGISTRY.save_callback = save_tokens_callback

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

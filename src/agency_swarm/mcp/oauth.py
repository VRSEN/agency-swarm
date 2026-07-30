"""OAuth authentication for MCP servers.

Provides OAuth 2.0 with PKCE support for MCP servers using the MCP Python SDK's OAuthClientProvider.
Supports unified local/SaaS token storage via RunHooks and contextvars.

This module owns the security-critical storage chain: the hooks set the user contextvar,
storage reads it per operation, bucket containment is checked, token files are written
owner-only, and callback keys include the user segment. The interactive browser/stdin
flow lives in :mod:`agency_swarm.mcp.oauth_flow`, the server configuration model in
:mod:`agency_swarm.mcp.oauth_config`, and the run hooks in
:mod:`agency_swarm.mcp.oauth_storage_hooks`; all of them are re-exported here so
``from agency_swarm.mcp.oauth import X`` keeps working for every previously exported name.
"""

import contextlib
import json
import logging
import os
import tempfile
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypedDict, cast

from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthToken,
)

from .oauth_flow import (
    _can_poll_stdin_for_callback,  # noqa: F401
    _can_use_local_callback_server,  # noqa: F401
    _listen_for_callback_once,  # noqa: F401
    _parse_callback_response,  # noqa: F401
    _prompt_for_callback_url,  # noqa: F401
    _prompt_for_callback_url_polling,  # noqa: F401
    default_callback_handler,
    default_redirect_handler,
)
from .oauth_user import build_oauth_cache_segment, build_oauth_user_segment

# Contextvar for per-user token isolation
_user_id_context: ContextVar[str | None] = ContextVar("oauth_user_id", default=None)
_runtime_context: ContextVar["OAuthRuntimeContext | None"] = ContextVar("oauth_runtime_context", default=None)


def set_oauth_user_id(user_id: str | None) -> None:
    """Set the current user ID for OAuth token isolation.

    This must be called before MCP server connections are established
    to ensure tokens are stored in the correct per-user directory.

    Args:
        user_id: The user ID to associate with OAuth tokens, or None for default.
    """
    _user_id_context.set(user_id)
    logger.debug(f"OAuth user_id context set to: {user_id}")


def get_oauth_user_id() -> str | None:
    """Get the current OAuth user ID from context."""
    return _user_id_context.get()


class TokenPayload(TypedDict, total=False):
    access_token: str
    token_type: Literal["Bearer"]
    expires_in: int | None
    scope: str | None
    refresh_token: str | None


OAuthRedirectHandler = Callable[[str], Awaitable[None]]
OAuthCallbackHandler = Callable[[], Awaitable[tuple[str, str | None]]]
OAuthRedirectHandlerFactory = Callable[[str | None], OAuthRedirectHandler]
OAuthCallbackHandlerFactory = Callable[[str | None], OAuthCallbackHandler]


@dataclass(frozen=True)
class OAuthRuntimeContext:
    """Request-scoped OAuth runtime context used by provider creation."""

    mode: Literal["saas_stream", "local_browser"]
    user_id: str | None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timeout: float | None = None
    redirect_handler_factory: OAuthRedirectHandlerFactory | None = None
    callback_handler_factory: OAuthCallbackHandlerFactory | None = None


def set_oauth_runtime_context(context: OAuthRuntimeContext | None) -> None:
    """Set request-scoped OAuth runtime context for the current task."""
    _runtime_context.set(context)
    if context is not None:
        _user_id_context.set(context.user_id)


def get_oauth_runtime_context() -> OAuthRuntimeContext | None:
    """Return the current request-scoped OAuth runtime context."""
    return _runtime_context.get()


@dataclass
class TokenCallbackRegistry:
    """Holds optional load/save callbacks for token persistence.

    Callback keys include the OAuth client namespace, server URL, and optional
    user segment so credentials cannot cross OAuth client registrations.
    """

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


def _ensure_private_dir(directory: Path) -> Path:
    """Create ``directory`` and enforce owner-only permissions on it."""
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    return directory


def _write_private_file(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` so the file is never readable by other users.

    The payload is written to an owner-only temporary file in the same directory and
    then renamed over the target, so no reader can observe a world-readable window.
    """
    handle_fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle_fd, "w") as handle:
            handle.write(content)
        os.replace(temp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            temp_path.unlink()
        raise


class FileTokenStorage:
    """File-based token storage for MCP OAuth with per-user isolation."""

    def __init__(
        self,
        cache_dir: Path,
        server_name: str,
        server_url: str | None = None,
        token_callbacks: TokenCallbackRegistry | None = None,
        client_identity: str | None = None,
    ):
        """Initialize file-based token storage.

        Args:
            cache_dir: Base directory for token storage
            server_name: Unique name for the MCP server
            server_url: Full MCP endpoint URL (used for storage isolation and callback identification)
            token_callbacks: Optional callback registry for custom persistence
            client_identity: Secret-free identity for the effective OAuth client configuration
        """
        self.base_cache_dir = cache_dir
        self.server_name = server_name
        self.server_url = server_url or server_name
        self.client_identity = client_identity or "default-client"
        self.server_cache_segment = self.build_server_cache_segment(
            server_name,
            self.server_url,
            self.client_identity,
        )
        self._token_callbacks = token_callbacks

    @staticmethod
    def build_server_cache_segment(
        server_name: str,
        server_url: str | None = None,
        client_identity: str | None = None,
    ) -> str:
        """Build the cache bucket used for one MCP endpoint and OAuth client."""
        endpoint = server_url or server_name
        server_identity = server_name if endpoint == server_name else f"{server_name}::{endpoint}"
        storage_identity = f"{server_identity}::oauth-client::{client_identity or 'default-client'}"
        return build_oauth_cache_segment(
            storage_identity,
            max_prefix_length=120,
        )

    def _get_user_cache_dir(self) -> Path:
        """Get cache directory for current user from contextvar."""
        base_dir = self.base_cache_dir.expanduser().resolve()
        user_dir = (base_dir / self._get_user_cache_segment()).resolve()
        try:
            user_dir.relative_to(base_dir)
        except ValueError as exc:
            # Never share a bucket on containment failure: that would mix users' credentials.
            raise ValueError(f"OAuth user bucket resolved outside the cache directory: {user_dir}") from exc

        _ensure_private_dir(base_dir)
        return _ensure_private_dir(user_dir)

    def _get_server_cache_dir(self) -> Path:
        """Get cache directory for current server under the current user."""
        user_dir = self._get_user_cache_dir()
        server_dir = (user_dir / self.server_cache_segment).resolve()
        try:
            server_dir.relative_to(user_dir.resolve())
        except ValueError as exc:
            # Never share a bucket on containment failure: that would mix servers' credentials.
            raise ValueError(f"OAuth server bucket resolved outside the user cache directory: {server_dir}") from exc
        return _ensure_private_dir(server_dir)

    def _legacy_token_file(self) -> Path | None:
        """Return legacy flat token file path for migration."""
        legacy_dir = self._get_legacy_user_cache_dir()
        if legacy_dir is None:
            return None
        return legacy_dir / f"{self.server_cache_segment}_tokens.json"

    def _legacy_client_file(self) -> Path | None:
        """Return legacy flat client file path for migration."""
        legacy_dir = self._get_legacy_user_cache_dir()
        if legacy_dir is None:
            return None
        return legacy_dir / f"{self.server_cache_segment}_client.json"

    def _get_user_cache_segment(self) -> str:
        """Return the current cache bucket name for the active user."""
        user_id = _user_id_context.get()
        if not user_id:
            return "default"
        return build_oauth_user_segment(user_id, max_prefix_length=120)

    def _get_legacy_user_cache_dir(self) -> Path | None:
        """Return the pre-hash user bucket when it is safe to migrate.

        Older releases sanitized the user ID directly into a filesystem bucket.
        That old scheme can collapse distinct IDs such as `john@example.com`
        and `john/example.com` into the same path, and it also stripped leading
        or trailing dots/underscores and truncated names at 120 characters.
        Only migrate buckets whose segment is already unambiguous so we never
        silently copy another user's cached credentials into the current hashed
        bucket.
        """
        user_id = _user_id_context.get()
        if not user_id:
            legacy_segment = "default"
        elif any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for ch in user_id):
            return None
        else:
            stripped_user_id = user_id.strip("._")
            if (
                stripped_user_id == ""
                or stripped_user_id == "default"
                or stripped_user_id != user_id
                or len(stripped_user_id) > 120
            ):
                return None
            legacy_segment = stripped_user_id

        base_dir = self.base_cache_dir.expanduser().resolve()
        legacy_dir = (base_dir / legacy_segment).resolve()
        try:
            legacy_dir.relative_to(base_dir)
        except ValueError:
            logger.warning("Legacy OAuth user bucket resolved outside cache dir; skipping migration.")
            return None
        return legacy_dir

    def _get_token_callback_key(self) -> str:
        """Return the callback persistence key for the active user context."""
        user_id = _user_id_context.get()
        if not user_id:
            return f"{self.server_cache_segment}::{self.server_url}"
        scoped_user = build_oauth_user_segment(user_id, max_prefix_length=120)
        return f"{scoped_user}::{self.server_cache_segment}::{self.server_url}"

    async def get_tokens(self) -> OAuthToken | None:
        """Get stored tokens for current user."""
        if self._token_callbacks and self._token_callbacks.load_callback:
            try:
                callback_key = self._get_token_callback_key()
                data = self._token_callbacks.load_callback(callback_key)
                if data:
                    return OAuthToken(**data)
            except Exception:
                logger.exception("OAuth load_tokens_callback failed")

        server_dir = self._get_server_cache_dir()
        token_file = server_dir / "tokens.json"

        if not token_file.exists():
            legacy_file = self._legacy_token_file()
            if legacy_file is None or not legacy_file.exists():
                return None
            try:
                data = cast("TokenPayload", json.loads(legacy_file.read_text()))
                tokens = OAuthToken(**data)
                _write_private_file(token_file, tokens.model_dump_json(indent=2))
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
        """Store tokens for current user.

        Persistence failures propagate: a silently dropped token makes the run look
        authenticated while the next request re-runs the whole OAuth flow.
        """
        server_dir = self._get_server_cache_dir()
        token_file = server_dir / "tokens.json"

        _write_private_file(token_file, tokens.model_dump_json(indent=2))
        logger.info(f"Tokens saved to {token_file}")
        # Clean up legacy flat file if it exists
        legacy_file = self._legacy_token_file()
        if legacy_file is not None:
            with contextlib.suppress(FileNotFoundError):
                legacy_file.unlink()
        if self._token_callbacks and self._token_callbacks.save_callback:
            payload = cast("TokenPayload", tokens.model_dump())
            callback_key = self._get_token_callback_key()
            self._token_callbacks.save_callback(callback_key, payload)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        """Get stored client information for current user."""
        server_dir = self._get_server_cache_dir()
        client_file = server_dir / "client.json"

        if not client_file.exists():
            legacy_file = self._legacy_client_file()
            if legacy_file is None or not legacy_file.exists():
                return None
            try:
                data = json.loads(legacy_file.read_text())
                client_info = OAuthClientInformationFull(**data)
                _write_private_file(client_file, client_info.model_dump_json(indent=2))
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
        """Store client information for current user.

        Persistence failures propagate for the same reason as :meth:`set_tokens`.
        """
        server_dir = self._get_server_cache_dir()
        client_file = server_dir / "client.json"

        _write_private_file(client_file, client_info.model_dump_json(indent=2))
        logger.info(f"Client info saved to {client_file}")
        legacy_file = self._legacy_client_file()
        if legacy_file is not None:
            with contextlib.suppress(FileNotFoundError):
                legacy_file.unlink()


# Compatibility re-exports, deferred to here on purpose: both modules read the
# contextvar and cache helpers defined above, so they can only be imported once those
# names exist. This keeps ``from agency_swarm.mcp.oauth import X`` working for every name
# this module used to own.
from .oauth_config import MCPServerOAuth  # noqa: E402
from .oauth_storage_hooks import OAuthStorageHooks  # noqa: E402, F401


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
            client_identity=server.get_client_identity(),
        )

    client_metadata = server.build_client_metadata()
    client_info = server.build_client_information()

    if client_info and hasattr(storage, "set_client_info"):
        await storage.set_client_info(client_info)

    runtime_context = get_oauth_runtime_context()
    runtime_redirect_handler: OAuthRedirectHandler | None = None
    runtime_callback_handler: OAuthCallbackHandler | None = None
    if runtime_context is not None:
        if runtime_context.redirect_handler_factory is not None:
            runtime_redirect_handler = runtime_context.redirect_handler_factory(server.name)
        if runtime_context.callback_handler_factory is not None:
            runtime_callback_handler = runtime_context.callback_handler_factory(server.name)

    # Handler precedence: explicit args > request context > server-level handlers > defaults
    redirect_handler = (
        redirect_handler or runtime_redirect_handler or server.redirect_handler or default_redirect_handler
    )
    if callback_handler is None:
        callback_handler = runtime_callback_handler or server.callback_handler
    if callback_handler is None:
        callback_timeout = runtime_context.timeout if runtime_context and runtime_context.timeout is not None else 300.0

        async def _wrapped_callback_handler() -> tuple[str, str | None]:
            redirect_uri = server.get_callback_redirect_uri(client_metadata)
            return await default_callback_handler(redirect_uri, timeout=callback_timeout)

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

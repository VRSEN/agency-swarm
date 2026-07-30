"""Optional OAuth wiring shared by the MCP manager modules.

Imports the OAuth implementation lazily so the manager keeps working when the MCP SDK is
absent, and owns the persistence-key, cache-directory and handler-resolution helpers that
every other MCP manager module builds on.
"""

import copy
import logging
from collections.abc import Awaitable, Callable, Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict, cast

from agency_swarm.mcp.oauth_user import build_oauth_user_segment

if TYPE_CHECKING:
    from mcp.client.auth import OAuthClientProvider

    from agency_swarm.mcp.oauth import MCPServerOAuth

logger = logging.getLogger(__name__)

OAuthRedirectHandler = Callable[[str], Awaitable[None]]
OAuthCallbackHandler = Callable[[], Awaitable[tuple[str, str | None]]]


class OAuthHandlerMap(TypedDict, total=False):
    redirect: OAuthRedirectHandler
    callback: OAuthCallbackHandler


# OAuth support - imported conditionally to avoid circular imports
_OAUTH_AVAILABLE = False
_MCPServerOAuth: type | None = None
_MCPServerOAuthClient: type | None = None
_create_oauth_provider: Callable[..., Coroutine[object, object, "OAuthClientProvider"]] | None = None
_set_oauth_user_id: Callable[[str | None], None] | None = None
_get_oauth_user_id: Callable[[], str | None] | None = None
_set_oauth_runtime_context: Callable[[Any | None], None] | None = None
_get_oauth_runtime_context: Callable[[], Any | None] | None = None

try:
    from agency_swarm.mcp.oauth import (
        MCPServerOAuth as _MCPServerOAuth_impl,
        create_oauth_provider as _create_oauth_provider_impl,
        get_oauth_runtime_context as _get_oauth_runtime_context_impl,
        get_oauth_user_id as _get_oauth_user_id_impl,
        set_oauth_runtime_context as _set_oauth_runtime_context_impl,
        set_oauth_user_id as _set_oauth_user_id_impl,
    )
    from agency_swarm.mcp.oauth_client import MCPServerOAuthClient as _MCPServerOAuthClient_impl

    _MCPServerOAuth = _MCPServerOAuth_impl
    _MCPServerOAuthClient = _MCPServerOAuthClient_impl
    _create_oauth_provider = _create_oauth_provider_impl
    _set_oauth_user_id = _set_oauth_user_id_impl
    _get_oauth_user_id = _get_oauth_user_id_impl
    _set_oauth_runtime_context = _set_oauth_runtime_context_impl
    _get_oauth_runtime_context = _get_oauth_runtime_context_impl
    _OAUTH_AVAILABLE = True
except ImportError:
    logger.debug("OAuth support not available - install MCP SDK to enable")

_MANAGED_OAUTH_CACHE_DIR_ATTR = "_agency_swarm_managed_oauth_cache_dir"


def get_active_oauth_user_id() -> str | None:
    """Return the OAuth user whose token bucket the current context is bound to."""
    if _get_oauth_user_id is None:
        return None
    return _get_oauth_user_id()


def _sanitize_oauth_registry_user_id(user_id: str) -> str:
    return build_oauth_user_segment(user_id, max_prefix_length=96)


def _oauth_store_key_segment(config: Any) -> str:
    storage = getattr(config, "storage", None)
    if storage is not None:
        return _sanitize_oauth_registry_user_id(f"storage:{id(storage)}")

    storage_factory = getattr(config, "storage_factory", None)
    if storage_factory is not None:
        return _sanitize_oauth_registry_user_id(f"storage_factory:{id(storage_factory)}")

    cache_dir = getattr(config, "cache_dir", None)
    if cache_dir is not None:
        path = Path(cache_dir).expanduser().resolve(strict=False)
        return _sanitize_oauth_registry_user_id(f"cache:{path}")

    return "default"


def _oauth_endpoint_key_segment(config: Any) -> str:
    url = getattr(config, "url", None)
    if not isinstance(url, str) or url == "":
        return "unknown-url"
    return _sanitize_oauth_registry_user_id(f"url:{url}")


def _oauth_request_key_suffix(request_id: str) -> str:
    return f"::{_sanitize_oauth_registry_user_id(f'request:{request_id}')}"


def _build_persistence_key(server: Any, oauth_user_id: str | None) -> str:
    """Build process-level persistence key for MCP servers.

    OAuth clients are keyed by server, endpoint, OAuth client identity, user,
    and token store to avoid cross-client, cross-user, or cross-agency reuse.
    Non-OAuth servers keep name-only keys.
    """
    actual = getattr(server, "_server", server)
    name = getattr(actual, "name", None)
    if not isinstance(name, str) or name == "":
        return ""
    if _MCPServerOAuthClient is None or not isinstance(actual, _MCPServerOAuthClient):
        return name
    if not isinstance(oauth_user_id, str) or oauth_user_id == "":
        user_segment = "default"
    else:
        user_segment = _sanitize_oauth_registry_user_id(oauth_user_id)
    oauth_client = cast(Any, actual)
    endpoint_segment = _oauth_endpoint_key_segment(oauth_client.oauth_config)
    client_segment = _sanitize_oauth_registry_user_id(f"client:{oauth_client.oauth_config.get_client_identity()}")
    store_segment = _oauth_store_key_segment(oauth_client.oauth_config)
    runtime_context = _get_oauth_runtime_context() if _get_oauth_runtime_context is not None else None
    runtime_request_id = getattr(runtime_context, "request_id", None) if runtime_context is not None else None
    if getattr(runtime_context, "mode", None) == "saas_stream" and isinstance(runtime_request_id, str):
        key_prefix = f"{name}::oauth::{endpoint_segment}::{client_segment}::{user_segment}::{store_segment}"
        return f"{key_prefix}{_oauth_request_key_suffix(runtime_request_id)}"
    return f"{name}::oauth::{endpoint_segment}::{client_segment}::{user_segment}::{store_segment}"


def apply_managed_oauth_cache_dir(config: Any, cache_dir: Path | None) -> None:
    """Apply an Agency-managed OAuth cache dir without overwriting explicit server config."""
    if cache_dir is None:
        return
    if getattr(config, "cache_dir", None) is None or bool(getattr(config, _MANAGED_OAUTH_CACHE_DIR_ATTR, False)):
        config.cache_dir = cache_dir
        setattr(config, _MANAGED_OAUTH_CACHE_DIR_ATTR, True)


def bind_managed_oauth_cache_dir(config: Any, cache_dir: Path | None) -> Any:  # noqa: ANN401
    """Bind an Agency-managed cache dir without retargeting another Agency's config."""
    if cache_dir is None:
        return config
    current = getattr(config, "cache_dir", None)
    is_managed = bool(getattr(config, _MANAGED_OAUTH_CACHE_DIR_ATTR, False))
    if current is not None and not is_managed:
        return config
    if is_managed and current != cache_dir:
        config = copy.copy(config)
    apply_managed_oauth_cache_dir(config, cache_dir)
    return config


def _clone_oauth_candidate(server: Any) -> Any:
    """Return a fresh OAuth client when the current object is already user-bound."""
    if not _OAUTH_AVAILABLE or _MCPServerOAuthClient is None:
        return server

    actual = getattr(server, "_server", server)
    if not isinstance(actual, _MCPServerOAuthClient):
        return server
    client = cast(Any, actual)

    runtime_context = _get_oauth_runtime_context() if _get_oauth_runtime_context is not None else None
    preserve_client_handlers = runtime_context is None or (
        client.oauth_config.redirect_handler is not None or client.oauth_config.callback_handler is not None
    )
    handlers: OAuthHandlerMap = {}
    if preserve_client_handlers and client._redirect_handler is not None:
        handlers["redirect"] = client._redirect_handler
    if preserve_client_handlers and client._callback_handler is not None:
        handlers["callback"] = client._callback_handler
    return _MCPServerOAuthClient(client.oauth_config, handlers or None)


def _current_oauth_handlers(client: Any) -> OAuthHandlerMap:
    """Return the handlers that should be active for the current OAuth request."""
    handlers: OAuthHandlerMap = {}
    if client._redirect_handler is not None:
        handlers["redirect"] = client._redirect_handler
    if client._callback_handler is not None:
        handlers["callback"] = client._callback_handler

    runtime_context = _get_oauth_runtime_context() if _get_oauth_runtime_context is not None else None
    if runtime_context is not None:
        if "redirect" not in handlers and runtime_context.redirect_handler_factory is not None:
            handlers["redirect"] = runtime_context.redirect_handler_factory(client.name)
        if "callback" not in handlers and runtime_context.callback_handler_factory is not None:
            handlers["callback"] = runtime_context.callback_handler_factory(client.name)

    if "redirect" not in handlers and client.oauth_config.redirect_handler is not None:
        handlers["redirect"] = client.oauth_config.redirect_handler
    if "callback" not in handlers and client.oauth_config.callback_handler is not None:
        handlers["callback"] = client.oauth_config.callback_handler
    return handlers


def _process_oauth_servers(agent: Any, servers: list[Any]) -> None:
    """Process OAuth-enabled MCP servers and convert them to authenticated clients.

    Args:
        agent: The agent instance
        servers: List of MCP server instances (may include MCPServerOAuth)
    """
    if not _OAUTH_AVAILABLE or _MCPServerOAuth is None:
        return

    # Import OAuth client here to avoid circular import
    from agency_swarm.mcp.oauth_client import MCPServerOAuthClient

    handler_factory = getattr(agent, "mcp_oauth_handler_factory", None)
    factory: Callable[[str], OAuthHandlerMap] | None = None
    if callable(handler_factory):
        factory = cast("Callable[[str], OAuthHandlerMap]", handler_factory)

    # Convert OAuth configs to OAuth clients
    for i, srv in enumerate(list(servers)):
        if not isinstance(srv, _MCPServerOAuth):
            continue

        oauth_srv = cast("MCPServerOAuth", srv)
        logger.info(f"Creating OAuth client for MCP server: {oauth_srv.name}")

        try:
            client_id = oauth_srv.get_client_id_optional()
            if client_id:
                logger.info(f"OAuth configured for {oauth_srv.name} (client_id: {client_id[:8]}...)")

            # Build handlers: config-level first. Factory remains a compatibility fallback.
            server_handlers: OAuthHandlerMap = {}
            if oauth_srv.redirect_handler:
                server_handlers["redirect"] = oauth_srv.redirect_handler
            if oauth_srv.callback_handler:
                server_handlers["callback"] = oauth_srv.callback_handler

            if factory is not None and not server_handlers:
                new_handlers = factory(oauth_srv.name)
                server_handlers.update(new_handlers)

            handlers_arg = server_handlers if server_handlers else None
            oauth_client = MCPServerOAuthClient(
                oauth_srv,
                handlers_arg,
            )

            # Replace config with actual client
            servers[i] = oauth_client
            logger.info(f"OAuth client created for {oauth_srv.name}")

        except Exception:
            logger.exception(f"Failed to create OAuth client for {oauth_srv.name}")
            raise


def _sync_oauth_client_handlers(persistent: object, candidate: object) -> bool:
    """Update cached OAuth client with per-request handlers from a new instance.

    Returns False because sessions are no longer invalidated when handlers refresh.
    """
    if not _OAUTH_AVAILABLE or _MCPServerOAuthClient is None:
        return False

    existing_client = getattr(persistent, "_server", persistent)
    new_client = getattr(candidate, "_server", candidate)

    if not isinstance(existing_client, _MCPServerOAuthClient) or not isinstance(new_client, _MCPServerOAuthClient):
        return False

    server_handlers = _current_oauth_handlers(cast(Any, new_client))
    if not server_handlers:
        return False

    client = cast(Any, existing_client)
    if "redirect" in server_handlers:
        client._redirect_handler = server_handlers["redirect"]
    if "callback" in server_handlers:
        client._callback_handler = server_handlers["callback"]
    provider = getattr(client, "_oauth_provider", None)
    provider_context = getattr(provider, "context", None) if provider is not None else None
    if provider_context is not None:
        if "redirect" in server_handlers:
            provider_context.redirect_handler = server_handlers["redirect"]
        if "callback" in server_handlers:
            provider_context.callback_handler = server_handlers["callback"]
    return False

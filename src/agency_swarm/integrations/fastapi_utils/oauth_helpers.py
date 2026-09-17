"""OAuth request context helpers shared by the endpoint handlers."""

import logging
import time
from typing import Any

from fastapi import HTTPException

from agency_swarm import Agency
from agency_swarm.integrations.fastapi_utils.oauth_support import (
    FastAPIOAuthConfig,
    FastAPIOAuthRuntime,
    has_hosted_mcp_oauth_tools,
    has_hosted_mcp_tools_missing_authorization,
    is_oauth_server,
)

# Keep the pre-split logger name so log records are unchanged.
logger = logging.getLogger("agency_swarm.integrations.fastapi_utils.endpoint_handlers")


OAUTH_KEEPALIVE_SECONDS = 15.0


def _sse_keepalive_comment() -> str:
    return f": keepalive {int(time.time())}\n\n"


def _update_oauth_pending(pending_states: set[str], payload: dict[str, Any]) -> None:
    state = payload.get("state")
    if not isinstance(state, str) or state == "":
        return
    event_type = payload.get("type")
    if event_type == "oauth_redirect":
        pending_states.add(state)
        return
    if event_type != "oauth_status":
        return
    status = payload.get("status")
    if status == "pending":
        pending_states.add(state)
        return
    if isinstance(status, str) and (status == "authorized" or status == "timeout" or status.startswith("error:")):
        pending_states.discard(state)


async def _no_oauth_user_id() -> None:
    return None


def _resolve_oauth_user_id(user_id: object, oauth_config: FastAPIOAuthConfig | None) -> str | None:
    if oauth_config is None:
        return None
    if not isinstance(user_id, str) or user_id.strip() == "":
        raise HTTPException(status_code=401, detail="OAuth authentication did not resolve a user ID")
    return user_id


def _set_oauth_user_context(user_id: str | None) -> None:
    """Set the OAuth user ID contextvar for per-user token isolation."""
    try:
        from agency_swarm.mcp.oauth import set_oauth_user_id

        set_oauth_user_id(user_id)
    except ImportError:
        pass


def _set_oauth_runtime_context(runtime: FastAPIOAuthRuntime | None, user_id: str | None) -> None:
    """Set request-scoped OAuth runtime context for provider creation."""
    try:
        from agency_swarm.mcp.oauth import OAuthRuntimeContext, set_oauth_runtime_context
    except ImportError:
        return

    if runtime is None:
        set_oauth_runtime_context(None)
        return

    set_oauth_runtime_context(
        OAuthRuntimeContext(
            mode="saas_stream",
            user_id=user_id,
            timeout=runtime.timeout,
            redirect_handler_factory=runtime.redirect_handler_factory(),
            callback_handler_factory=runtime.callback_handler_factory(),
        )
    )


def _clear_oauth_request_context() -> None:
    _set_oauth_user_context(None)
    _set_oauth_runtime_context(None, None)


def _prepare_oauth_runtime(
    agency_instance: Agency,
    oauth_runtime: FastAPIOAuthRuntime | None,
    user_id: str | None,
) -> FastAPIOAuthRuntime | None:
    """Attach per-request OAuth helpers and propagate user_id."""
    _set_oauth_user_context(user_id)
    _set_oauth_runtime_context(oauth_runtime, user_id)

    agents_map = getattr(agency_instance, "agents", None)
    if oauth_runtime is None:
        if isinstance(agents_map, dict):
            for agent in agents_map.values():
                agent._hosted_mcp_oauth_enabled = False
        return None

    if oauth_runtime is not None:
        if isinstance(agents_map, dict):
            for agent in agents_map.values():
                oauth_runtime.install_handler_factory(agent)

    return oauth_runtime


def _with_oauth_user_context(user_context: dict[str, Any] | None, user_id: str | None) -> dict[str, Any] | None:
    """Return request context with header user_id included without mutating shared agency state."""
    if user_id is None:
        return user_context
    merged_context = dict(user_context or {})
    merged_context["user_id"] = user_id
    return merged_context


def _has_oauth_servers(agency_instance: Agency) -> bool:
    agents_map = getattr(agency_instance, "agents", {})
    if not isinstance(agents_map, dict):
        return False
    for agent in agents_map.values():
        servers = getattr(agent, "mcp_servers", None)
        if isinstance(servers, list) and any(is_oauth_server(srv) for srv in servers):
            return True
        deferred_oauth_servers = getattr(agent, "_oauth_mcp_servers", None)
        if isinstance(deferred_oauth_servers, dict) and any(
            is_oauth_server(srv) for srv in deferred_oauth_servers.values()
        ):
            return True
    return False


def _ensure_request_oauth_config(
    agency_instance: Agency,
    oauth_config: FastAPIOAuthConfig | None,
) -> None:
    """Reject request-time OAuth capabilities missed by the startup preview."""
    if oauth_config is not None:
        return
    if _has_oauth_servers(agency_instance) or has_hosted_mcp_tools_missing_authorization(agency_instance):
        raise HTTPException(
            status_code=500,
            detail=(
                "The agency factory returned OAuth-enabled agents that were not present during FastAPI startup. "
                "Ensure the startup factory preview exposes OAuth and configure oauth_user_id_dependency."
            ),
        )


def _has_enabled_hosted_mcp_oauth(agency_instance: Agency) -> bool:
    agents_map = getattr(agency_instance, "agents", {})
    if not isinstance(agents_map, dict):
        return False
    return any(bool(getattr(agent, "_hosted_mcp_oauth_enabled", False)) for agent in agents_map.values())


def _requires_oauth_agent_state_restore(agency_instance: Agency, oauth_runtime: FastAPIOAuthRuntime | None) -> bool:
    return oauth_runtime is not None and (
        _has_oauth_servers(agency_instance)
        or _has_enabled_hosted_mcp_oauth(agency_instance)
        or (oauth_runtime.enable_hosted_mcp_oauth and has_hosted_mcp_oauth_tools(agency_instance))
    )

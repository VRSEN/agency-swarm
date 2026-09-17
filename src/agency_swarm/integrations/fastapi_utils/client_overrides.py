"""Request-scoped OpenAI client construction and application."""

import logging

from agents import ModelSettings
from fastapi import Request
from openai import AsyncOpenAI, OpenAI

from agency_swarm import Agency, Agent
from agency_swarm.integrations.fastapi_utils import endpoint_handlers
from agency_swarm.integrations.fastapi_utils.codex_compat import _apply_codex_compatibility_model_settings
from agency_swarm.integrations.fastapi_utils.litellm_client_config import (
    _agent_supports_openai_client_override,
    _agent_uses_litellm,
    _apply_client_to_agent,
    _get_litellm_provider,
    _is_litellm_model,
    _is_local_litellm_provider,
    _log_unsupported_client_override,
)
from agency_swarm.integrations.fastapi_utils.model_override import (
    _apply_request_model_override,
    _refresh_framework_defaults_after_model_swap,
)
from agency_swarm.integrations.fastapi_utils.model_settings_extra_args import (
    _apply_request_model_settings_extra_args,
)
from agency_swarm.integrations.fastapi_utils.override_policy import (
    _get_cached_openai_client_from_agent,
    _get_openai_client_from_agent,
)
from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
from agency_swarm.messages.codex_input import is_codex_base_url as _is_codex_base_url
from agency_swarm.utils import hosted_tool_compat
from agency_swarm.utils.openrouter import get_openrouter_model_name, is_openrouter_model_name

# Keep the pre-split logger name so log records are unchanged.
logger = logging.getLogger("agency_swarm.integrations.fastapi_utils.endpoint_handlers")


_AGENCY_SWARM_DEFAULT_MODEL = "agency-swarm/default"


def apply_openai_client_config(agency: Agency, config: ClientConfig) -> None:
    """Apply custom OpenAI client configuration to all agents in the agency.

    Creates a new AsyncOpenAI client with the provided base_url and/or api_key,
    optionally sets every agent's model from ``config.model``, then updates each
    agent's model to use this client. This allows per-request client configuration
    without rebuilding templates.

    Parameters
    ----------
    agency : Agency
        The agency instance to configure.
    config : ClientConfig
        Configuration containing base_url, api_key, optional ``model``, and other overrides.
    """
    if (
        config.base_url is None
        and config.api_key is None
        and config.default_headers is None
        and config.litellm_keys is None
        and config.model is None
        and config.model_settings_extra_args is None
    ):
        return  # Nothing to override

    openai_overrides_present = (
        config.base_url is not None or config.api_key is not None or config.default_headers is not None
    )
    litellm_overrides_present = (
        config.base_url is not None or config.api_key is not None or config.litellm_keys is not None
    )

    # Apply to all agents in the agency
    for agent in agency.agents.values():
        gateway_applied = False
        if config.model is not None:
            gateway_applied = _apply_request_model_override(agent, config.model, config)
            _refresh_framework_defaults_after_model_swap(agent)
        _apply_request_model_settings_extra_args(agent, config)

        # File attachment handling uses agent.client / agent.client_sync directly.
        # Keep those clients request-scoped too, so file_ids work without server env keys.
        if openai_overrides_present:
            if _uses_openrouter_request_client(agent, config):
                _apply_openrouter_file_clients_to_agent(agent)
            else:
                _apply_request_scoped_openai_clients_to_agent(agent, config)

        if _agent_uses_litellm(agent):
            if config.default_headers is not None:
                _apply_default_headers_to_agent_model_settings(agent, config.default_headers)
            if litellm_overrides_present:
                _apply_client_to_agent(agent, None, config)
        elif openai_overrides_present:
            if gateway_applied:
                # Gateway client was already routed through the freshly rebuilt model.
                if config.default_headers is not None:
                    _apply_default_headers_to_agent_model_settings(agent, config.default_headers)
                if _is_codex_base_url(config.base_url):
                    _apply_codex_compatibility_model_settings(agent)
            elif not _agent_supports_openai_client_override(agent):
                _log_unsupported_client_override(agent)
            else:
                client = endpoint_handlers._build_openai_client_for_agent(agent, config)
                if client is None:
                    if config.default_headers is not None:
                        _apply_default_headers_to_agent_model_settings(agent, config.default_headers)
                else:
                    _apply_client_to_agent(agent, client, config)

        hosted_tool_compat.apply_openai_hosted_tool_compatibility(agent)


def _resolve_stream_client_config(http_request: Request, config: ClientConfig | None) -> ClientConfig | None:
    if config is None:
        return None
    app_state = getattr(getattr(http_request, "app", None), "state", None)
    if not bool(getattr(app_state, "agency_swarm_tui_bridge", False)):
        return config
    if config.model is not None and _is_litellm_model(config.model):
        provider = _get_litellm_provider(config.model)
        if (
            config.base_url is not None
            and _is_local_litellm_provider(provider)
            and _is_request_base_url(http_request, config.base_url)
        ):
            return config.model_copy(update={"base_url": None})
    if config.model != _AGENCY_SWARM_DEFAULT_MODEL:
        return config
    update: dict[str, str | None] = {"model": None}
    if config.base_url is not None and _is_request_base_url(http_request, config.base_url):
        update["base_url"] = None
    return config.model_copy(update=update)


def _is_request_base_url(http_request: Request, base_url: str) -> bool:
    request_base_url = getattr(http_request, "base_url", None)
    if request_base_url is None:
        return False
    return str(request_base_url).rstrip("/") == base_url.rstrip("/")


def _build_openai_client_for_agent(agent: Agent, config: ClientConfig) -> AsyncOpenAI | None:
    """Build an AsyncOpenAI client by layering config over existing defaults.

    Priority:
    - explicit values from `config` win
    - otherwise fall back to the agent's existing OpenAI client (if any)
    - otherwise fall back to the global default OpenAI client (if any)
    - otherwise:
      - if `config` only includes default_headers, skip client replacement (no baseline client to copy)
      - else create a fresh AsyncOpenAI() using environment variables/request overrides
    """
    base_client = _get_openai_client_from_agent(agent) or endpoint_handlers.get_default_openai_client()

    if base_client is None:
        if config.api_key is None and config.base_url is None:
            return None
        # Allow request-provided api_key/base_url to work even when the server has no OPENAI_API_KEY.
        return AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            default_headers=config.default_headers,
        )

    # Only override the values that are explicitly provided in `config`.
    # OpenAI's `copy()` also handles merging default headers correctly.
    return base_client.copy(
        api_key=config.api_key,
        base_url=config.base_url,
        default_headers=config.default_headers,
    )


def _build_request_scoped_openai_client(agent: Agent, config: ClientConfig) -> AsyncOpenAI | None:
    """Build a request-scoped AsyncOpenAI client for direct agent client access paths."""
    base_client = (
        _get_openai_client_from_agent(agent)
        or getattr(agent, "_openai_client", None)
        or endpoint_handlers.get_default_openai_client()
    )
    if base_client is None:
        # No existing client to copy from. Without an explicit api_key we can't build one safely.
        if config.api_key is None:
            return None
        return AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            default_headers=config.default_headers,
        )

    return base_client.copy(
        api_key=config.api_key,
        base_url=config.base_url,
        default_headers=config.default_headers,
    )


def _apply_request_scoped_openai_clients_to_agent(agent: Agent, config: ClientConfig) -> None:
    """Apply request-scoped async+sync OpenAI clients used by attachment/file managers."""
    async_client = _build_request_scoped_openai_client(agent, config)
    if async_client is None:
        return

    _apply_openai_clients_to_agent(agent, async_client)


def _uses_openrouter_request_client(agent: Agent, config: ClientConfig) -> bool:
    if isinstance(config.model, str) and is_openrouter_model_name(config.model):
        return True
    return get_openrouter_model_name(agent.model) is not None


def _apply_openrouter_file_clients_to_agent(agent: Agent) -> None:
    """Keep direct file clients off the OpenRouter chat client."""
    async_client = _get_cached_openai_client_from_agent(agent) or endpoint_handlers.get_default_openai_client()
    if async_client is None:
        return

    _apply_openai_clients_to_agent(agent, async_client)


def _apply_openai_clients_to_agent(agent: Agent, async_client: AsyncOpenAI) -> None:
    """Apply async and sync OpenAI clients used by direct file access paths."""
    agent._openai_client = async_client
    sync_base_url = str(async_client.base_url) if getattr(async_client, "base_url", None) is not None else None
    sync_headers_raw = async_client.default_headers
    sync_headers: dict[str, str] | None = None
    if sync_headers_raw is not None:
        # AsyncOpenAI headers may include non-string sentinel values; sync client expects plain str headers.
        sync_headers = {key: value for key, value in sync_headers_raw.items() if isinstance(value, str)}
    agent._openai_client_sync = OpenAI(
        api_key=async_client.api_key,
        base_url=sync_base_url,
        default_headers=sync_headers,
    )


def _apply_default_headers_to_agent_model_settings(agent: Agent, headers: dict[str, str]) -> None:
    """Merge request headers into this agent's ModelSettings.extra_headers."""
    if not headers:
        return
    current: ModelSettings = getattr(agent, "model_settings", None) or ModelSettings()
    existing = dict(current.extra_headers or {})
    merged = {**existing, **headers}
    # ModelSettings is a dataclass (agents==0.6.4), so updating requires replacement.
    current.extra_headers = merged
    agent.model_settings = current

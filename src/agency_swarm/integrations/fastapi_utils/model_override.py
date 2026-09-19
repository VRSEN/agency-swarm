"""Per-request model override machinery (OpenAI/OpenRouter/LiteLLM swaps)."""

import copy
import logging
import os
from typing import Any, cast

from agents import ModelSettings, OpenAIChatCompletionsModel, OpenAIResponsesModel

# LiteLLM is optional - only available if the `litellm` extra is installed
try:
    from agents.extensions.models.litellm_model import LitellmModel

    _LITELLM_AVAILABLE = True
except ImportError:
    _LITELLM_AVAILABLE = False
    LitellmModel = None  # type: ignore[misc, assignment]
from openai import AsyncOpenAI

from agency_swarm import Agent
from agency_swarm.agent.initialization import apply_framework_defaults
from agency_swarm.integrations.fastapi_utils import endpoint_handlers
from agency_swarm.integrations.fastapi_utils.litellm_client_config import (
    _is_litellm_model,
    _normalize_litellm_model_name,
    _should_reuse_source_openai_client,
    _should_wrap_openrouter_override_with_openai_client,
)
from agency_swarm.integrations.fastapi_utils.override_policy import _get_openai_client_from_agent
from agency_swarm.integrations.fastapi_utils.override_session import _has_request_openai_overrides
from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
from agency_swarm.utils.openrouter import (
    OPENROUTER_API_KEY_ENV,
    OPENROUTER_BASE_URL,
    build_openrouter_chat_model,
    get_openrouter_model_name,
    is_openrouter_model_name,
)

# Keep the pre-split logger name so log records are unchanged.
logger = logging.getLogger("agency_swarm.integrations.fastapi_utils.endpoint_handlers")


def _apply_request_model_override(agent: Agent, model_name: str, config: ClientConfig | None = None) -> bool:
    """Set ``agent.model`` to ``model_name`` for this request, preserving existing wiring.

    A per-request model swap must not silently discard the agent's embedded
    OpenAI client, wrapped model subtype, or LiteLLM credentials. Replace only
    the ``.model`` attribute of the current wrapper and keep everything else.

    - ``OpenAIResponsesModel`` / ``OpenAIChatCompletionsModel`` keep their
      embedded ``AsyncOpenAI`` client and their transport (Responses vs
      ChatCompletions). The model name is swapped in place. Any post-construction
      usage alias (e.g. ``_agency_swarm_usage_model_name`` set by the OpenClaw
      adapter) is carried across the rebuild so cost tracking stays correct.
    - ``LitellmModel`` keeps its existing ``base_url`` / ``api_key`` and only
      the model identifier is swapped.
    - Bare-string agents become bare strings (or a minimal ``LitellmModel`` for
      ``litellm/...`` names).

    When ``config`` carries OpenAI gateway overrides (``base_url`` / ``api_key`` /
    ``default_headers``), the rebuilt OpenAI wrapper is routed through
    :func:`_build_openai_client_for_agent` so the request gateway reaches the
    swapped model when the target is OpenAI-compatible or an explicit gateway
    ``base_url`` is supplied.

    Returns ``True`` when the OpenAI gateway client has already been applied
    during the swap so the caller can skip the downstream client-apply step.
    """
    model = agent.model

    if is_openrouter_model_name(model_name):
        source_openrouter_model = get_openrouter_model_name(model)
        gateway_client = None
        openrouter_client = None
        source_default_headers: dict[str, str] | None = None
        if source_openrouter_model is not None:
            gateway_client = _resolve_request_gateway_client(agent, config)
            openrouter_client = gateway_client if gateway_client is not None else _get_openai_client_from_agent(agent)
        elif _has_request_openai_overrides(config):
            source_client = _get_openai_client_from_agent(agent)
            if source_client is not None and _should_copy_source_openai_client_for_openrouter(source_client, config):
                openrouter_client = _copy_source_openai_client_for_openrouter(source_client, config)
        else:
            source_client = _get_openai_client_from_agent(agent)
            if _should_reuse_source_openai_client(source_client):
                openrouter_client = source_client
            elif source_client is not None and _should_copy_source_openai_client_for_openrouter(source_client):
                openrouter_client = _copy_source_openai_client_for_openrouter(source_client, config)
            elif source_client is not None and _should_preserve_source_openai_headers(source_client):
                source_default_headers = _copyable_source_openai_headers(source_client)
        agent.model = build_openrouter_chat_model(
            model_name,
            api_key=None if openrouter_client is not None or config is None else config.api_key,
            base_url=None if openrouter_client is not None or config is None else config.base_url,
            default_headers=_openrouter_override_default_headers(config, openrouter_client, source_default_headers),
            openai_client=openrouter_client,
            should_replay_reasoning_content=getattr(model, "should_replay_reasoning_content", None),
        )
        return gateway_client is not None or (source_openrouter_model is None and _has_request_openai_overrides(config))

    if get_openrouter_model_name(model) is not None:
        if _is_litellm_model(model_name):
            _apply_request_litellm_model(agent, model_name)
            return False
        if not _should_wrap_openrouter_override_with_openai_client(model_name, config):
            agent.model = model_name
            return False
        client = _resolve_openai_client_after_openrouter_override(config)
        if client is None:
            agent.model = model_name
            return False
        agent.model = OpenAIChatCompletionsModel(model=model_name, openai_client=client)
        return _has_request_openai_overrides(config)

    gateway_client = _resolve_request_gateway_client(agent, config)

    if isinstance(model, OpenAIResponsesModel):
        if _is_litellm_model(model_name):
            _apply_request_litellm_model(agent, model_name)
            return False
        client = gateway_client if gateway_client is not None else model._client
        agent.model = _rebuild_openai_responses_model(model, model_name, client)
        return gateway_client is not None

    if isinstance(model, OpenAIChatCompletionsModel):
        if _is_litellm_model(model_name):
            _apply_request_litellm_model(agent, model_name)
            return False
        client = gateway_client if gateway_client is not None else model._client
        agent.model = OpenAIChatCompletionsModel(model=model_name, openai_client=client)
        return gateway_client is not None

    if _LITELLM_AVAILABLE and LitellmModel is not None and isinstance(model, LitellmModel):
        actual = _normalize_litellm_model_name(model_name)
        agent.model = LitellmModel(model=actual, base_url=model.base_url, api_key=model.api_key)
        return False

    if _is_litellm_model(model_name):
        _apply_request_litellm_model(agent, model_name)
        return False

    if gateway_client is not None:
        # Wrap bare-string swaps through the request gateway client so provider-prefixed
        # names (e.g. "anthropic/claude-sonnet-4") still reach the gateway — the downstream
        # _agent_supports_openai_client_override gate rejects those names and would
        # otherwise drop the request-scoped client entirely.
        agent.model = OpenAIResponsesModel(model=model_name, openai_client=gateway_client)
        return True

    agent.model = model_name
    return False


def _resolve_request_gateway_client(agent: Agent, config: ClientConfig | None) -> AsyncOpenAI | None:
    """Return a request-scoped OpenAI gateway client when ``config`` asks for one."""
    if config is None:
        return None
    if config.base_url is None and config.api_key is None and config.default_headers is None:
        return None
    return endpoint_handlers._build_openai_client_for_agent(agent, config)


def _should_preserve_source_openai_headers(client: AsyncOpenAI | None) -> bool:
    if client is None:
        return False
    if client is endpoint_handlers.get_default_openai_client():
        return False
    base_url = str(client.base_url).rstrip("/")
    if base_url != "https://api.openai.com/v1":
        return False
    return bool(_copyable_source_openai_headers(client))


def _should_copy_source_openai_client_for_openrouter(
    client: AsyncOpenAI | None,
    config: ClientConfig | None = None,
) -> bool:
    if client is None:
        return False
    if client is endpoint_handlers.get_default_openai_client():
        return False
    base_url = str(client.base_url).rstrip("/")
    if base_url != "https://api.openai.com/v1":
        return False
    return bool((None if config is None else config.api_key) or os.getenv(OPENROUTER_API_KEY_ENV))


def _copy_source_openai_client_for_openrouter(
    client: AsyncOpenAI,
    config: ClientConfig | None,
) -> AsyncOpenAI:
    return client.copy(
        api_key=(None if config is None else config.api_key) or os.getenv(OPENROUTER_API_KEY_ENV),
        base_url=(None if config is None else config.base_url) or OPENROUTER_BASE_URL,
        default_headers=(None if config is None else config.default_headers) or _copyable_source_openai_headers(client),
    )


_OPENAI_CREDENTIAL_HEADER_NAMES = frozenset({"authorization", "openai-organization", "openai-project"})


def _copyable_source_openai_headers(client: AsyncOpenAI) -> dict[str, str] | None:
    headers = {
        key: value
        for key, value in cast(dict[str, str], dict(client.default_headers or {})).items()
        if key.lower() not in _OPENAI_CREDENTIAL_HEADER_NAMES
    }
    return headers or None


def _openrouter_override_default_headers(
    config: ClientConfig | None,
    openrouter_client: AsyncOpenAI | None,
    source_default_headers: dict[str, str] | None,
) -> dict[str, str] | None:
    if openrouter_client is not None:
        return None
    if config is not None and config.default_headers is not None:
        return config.default_headers
    return source_default_headers


def _resolve_openai_client_after_openrouter_override(config: ClientConfig | None) -> AsyncOpenAI | None:
    """Build a non-OpenRouter OpenAI client when an OpenRouter wrapper swaps away."""
    base_client = endpoint_handlers.get_default_openai_client()
    if config is None:
        return base_client
    if base_client is None:
        if config.api_key is None and config.base_url is None:
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


def _rebuild_openai_responses_model(
    source: OpenAIResponsesModel,
    model_name: str,
    client: AsyncOpenAI,
) -> OpenAIResponsesModel:
    """Rebuild ``OpenAIResponsesModel`` while preserving OpenClaw-scoped aliases.

    Both ``_agency_swarm_default_model_name`` (drives OpenClaw default-settings
    lookup) and ``_agency_swarm_usage_model_name`` (maps the wrapper's ``.model``
    to an upstream provider model for cost tracking) are scoped to the exact
    (model name, base URL) OpenClaw registration that produced them. Carrying
    either across a change in model name OR base URL would apply the wrong
    family defaults / mis-label usage — e.g. keeping ``openclaw:main`` but
    pointing at a new gateway invalidates the original registration. Only copy
    the aliases when BOTH identifiers still match the source.
    """
    rebuilt = OpenAIResponsesModel(model=model_name, openai_client=client)
    same_identity = rebuilt.model == source.model and _client_base_url(client) == _client_base_url(source._client)
    if not same_identity:
        return rebuilt
    default_alias = getattr(source, "_agency_swarm_default_model_name", None)
    if isinstance(default_alias, str) and default_alias:
        rebuilt._agency_swarm_default_model_name = default_alias  # type: ignore[attr-defined]
    usage_alias = getattr(source, "_agency_swarm_usage_model_name", None)
    if isinstance(usage_alias, str) and usage_alias:
        rebuilt._agency_swarm_usage_model_name = usage_alias  # type: ignore[attr-defined]
    return rebuilt


def _client_base_url(client: AsyncOpenAI) -> str:
    """Return the normalized base URL for an OpenAI client, for identity comparison."""
    base_url = getattr(client, "base_url", None)
    return str(base_url).rstrip("/") if base_url is not None else ""


# Fields that `agents.models.default_models.get_default_model_settings` varies by
# model family (currently the GPT-5 family sets these non-None). Keep this list
# in lockstep with that SDK helper — refreshing any other fields would drop
# caller-explicit generation tuning on a per-request model swap.
_MODEL_FAMILY_DEFAULT_FIELDS: tuple[str, ...] = ("reasoning", "verbosity")


def _refresh_framework_defaults_after_model_swap(agent: Agent) -> None:
    """Re-layer model-family defaults for the new ``agent.model`` without wiping caller fields.

    ``apply_framework_defaults`` treats any non-None field on the input
    ``ModelSettings`` as caller-explicit and preserves it. So to force a fresh
    model-family default (e.g. GPT-5's ``reasoning.effort`` / ``verbosity``
    bleeding into a GPT-4o swap) we clear ONLY the family-scoped fields on a
    copy of the previous settings and let ``apply_framework_defaults`` recompute
    them for the new model. Every other caller-tuned field (``temperature``,
    ``max_tokens``, ``top_p``, ``parallel_tool_calls``, ``extra_headers``, ...)
    survives untouched.
    """
    previous: ModelSettings | None = getattr(agent, "model_settings", None)
    cleared = copy.deepcopy(previous) if previous is not None else ModelSettings()
    for field_name in _MODEL_FAMILY_DEFAULT_FIELDS:
        setattr(cleared, field_name, None)

    kwargs: dict[str, Any] = {"model": agent.model, "model_settings": cleared}
    apply_framework_defaults(kwargs)
    agent.model_settings = cast(ModelSettings, kwargs["model_settings"])


def _apply_request_litellm_model(agent: Agent, model_name: str) -> None:
    """Build a fresh ``LitellmModel`` for the request when the original wrapper was not LiteLLM."""
    if not _LITELLM_AVAILABLE or LitellmModel is None:
        logger.warning(
            "Cannot apply client_config.model to agent '%s': model %r requires litellm "
            "(install the `litellm` extra: `uv add 'agency-swarm[litellm]'` or "
            "`pip install litellm --no-deps` after `pip install agency-swarm`)",
            agent.name,
            model_name,
        )
        return
    actual = _normalize_litellm_model_name(model_name)
    agent.model = LitellmModel(model=actual, base_url=None, api_key=None)

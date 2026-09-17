"""LiteLLM/OpenAI model predicates and per-request client application."""

import logging

from agents import Model, OpenAIChatCompletionsModel, OpenAIResponsesModel

# LiteLLM is optional - only available if openai-agents[litellm] is installed
try:
    from agents.extensions.models.litellm_model import LitellmModel

    _LITELLM_AVAILABLE = True
except ImportError:
    _LITELLM_AVAILABLE = False
    LitellmModel = None  # type: ignore[misc, assignment]
from openai import AsyncOpenAI

from agency_swarm import Agent
from agency_swarm.integrations.fastapi_utils.codex_compat import _apply_codex_compatibility_model_settings
from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
from agency_swarm.messages.codex_input import is_codex_base_url as _is_codex_base_url
from agency_swarm.utils.openrouter import (
    OPENROUTER_BASE_URL,
    build_openrouter_chat_model,
    get_openrouter_model_name,
)

# Keep the pre-split logger name so log records are unchanged.
logger = logging.getLogger("agency_swarm.integrations.fastapi_utils.endpoint_handlers")


def _should_reuse_source_openai_client(client: AsyncOpenAI | None) -> bool:
    if client is None:
        return False
    base_url = str(client.base_url).rstrip("/")
    return base_url == OPENROUTER_BASE_URL


def _is_litellm_model(model_name: str) -> bool:
    """Check if a model name is a LiteLLM model (uses litellm/ prefix)."""
    return model_name.startswith("litellm/")


def _normalize_litellm_model_name(model_name: str) -> str:
    actual = model_name[8:] if model_name.startswith("litellm/") else model_name
    provider, sep, rest = actual.partition("/")
    if sep and provider.lower() == "google":
        return f"gemini/{rest}"
    return actual


def _is_openai_model_name(model_name: str) -> bool:
    """Return True if a model name should be treated as OpenAI-compatible.

    The Agents SDK's MultiProvider treats:
    - no prefix (e.g. "gpt-4o") as OpenAI
    - "openai/<model>" as OpenAI

    For any other prefix (e.g. "anthropic/<model>"), we should NOT wrap into
    OpenAIResponsesModel, since that would route through the OpenAI client.
    """
    if "/" not in model_name:
        return True
    prefix, _rest = model_name.split("/", 1)
    return prefix == "openai"


def _should_wrap_openrouter_override_with_openai_client(model_name: str, config: ClientConfig | None) -> bool:
    if _is_openai_model_name(model_name):
        return True
    return config is not None and config.base_url is not None


def _get_model_name_for_override_logging(agent: Agent) -> str | None:
    """Return a human-friendly model identifier for override logs."""
    model = agent.model
    if isinstance(model, str):
        return model
    if isinstance(model, OpenAIResponsesModel | OpenAIChatCompletionsModel):
        return model.model
    if isinstance(model, Model):
        model_name = getattr(model, "model", None)
        if isinstance(model_name, str):
            return model_name
    return None


def _agent_supports_openai_client_override(agent: Agent) -> bool:
    """Return True only when request OpenAI client overrides are applicable."""
    if get_openrouter_model_name(agent.model) is not None:
        return True
    model_name = _get_model_name_for_override_logging(agent)
    if model_name is None:
        return False
    return _is_openai_model_name(model_name)


def _log_unsupported_client_override(agent: Agent) -> None:
    model_name = _get_model_name_for_override_logging(agent)
    if model_name is not None:
        logger.warning(
            "Skipping client_config for agent '%s': custom model '%s' is not supported for "
            "client override (only OpenAI models or 'litellm/' models are supported)",
            agent.name,
            model_name,
        )
        return

    logger.warning(
        "Cannot apply client config to agent '%s': unsupported model type %s",
        agent.name,
        type(agent.model).__name__,
    )


def _build_openai_model_for_client(model_name: str, client: AsyncOpenAI, *, chat: bool = False) -> Model:
    if _should_reuse_source_openai_client(client):
        return build_openrouter_chat_model(model_name, openai_client=client)
    if chat:
        return OpenAIChatCompletionsModel(model=model_name, openai_client=client)
    return OpenAIResponsesModel(model=model_name, openai_client=client)


def _apply_client_to_agent(agent: Agent, client: AsyncOpenAI | None, config: ClientConfig) -> None:
    """Apply a custom OpenAI client to an agent's model."""
    model = agent.model
    has_litellm_overrides = config.base_url is not None or config.api_key is not None or config.litellm_keys is not None

    if isinstance(model, str):
        if _is_litellm_model(model):
            if has_litellm_overrides:
                _apply_litellm_config(agent, model, config)
        elif not _is_openai_model_name(model):
            logger.warning(
                "Skipping client_config for agent '%s': custom model '%s' is not supported for "
                "client override (only OpenAI models or 'litellm/' models are supported)",
                agent.name,
                model,
            )
        else:
            if client is None:
                return
            agent.model = _build_openai_model_for_client(model, client)
            if _is_codex_base_url(str(client.base_url)):
                _apply_codex_compatibility_model_settings(agent)
    elif isinstance(model, OpenAIResponsesModel):
        if _is_litellm_model(model.model):
            if has_litellm_overrides:
                _apply_litellm_config(agent, model.model, config)
        elif not _is_openai_model_name(model.model):
            logger.warning(
                "Skipping client_config for agent '%s': custom model '%s' is not supported for "
                "client override (only OpenAI models or 'litellm/' models are supported)",
                agent.name,
                model.model,
            )
        else:
            if client is None:
                return
            agent.model = _build_openai_model_for_client(model.model, client)
            if _is_codex_base_url(str(client.base_url)):
                _apply_codex_compatibility_model_settings(agent)
    elif isinstance(model, OpenAIChatCompletionsModel):
        openrouter_model_name = get_openrouter_model_name(model)
        if openrouter_model_name is not None:
            if client is None:
                return
            agent.model = build_openrouter_chat_model(
                openrouter_model_name,
                openai_client=client,
                should_replay_reasoning_content=getattr(model, "should_replay_reasoning_content", None),
            )
            return
        if _is_litellm_model(model.model):
            if has_litellm_overrides:
                _apply_litellm_config(agent, model.model, config)
        elif not _is_openai_model_name(model.model):
            logger.warning(
                "Skipping client_config for agent '%s': custom model '%s' is not supported for "
                "client override (only OpenAI models or 'litellm/' models are supported)",
                agent.name,
                model.model,
            )
        else:
            if client is None:
                return
            agent.model = _build_openai_model_for_client(model.model, client, chat=True)
    elif _LITELLM_AVAILABLE and LitellmModel is not None and isinstance(model, LitellmModel):
        if has_litellm_overrides:
            # Preserve existing settings unless explicitly overridden.
            resolved_model = _normalize_litellm_model_name(model.model)
            base_url = _resolve_litellm_base_url(resolved_model, config, existing_base_url=model.base_url)
            api_key = _resolve_litellm_api_key(resolved_model, config, existing_api_key=model.api_key)
            agent.model = LitellmModel(model=model.model, base_url=base_url, api_key=api_key)
    elif isinstance(model, Model):
        model_name = getattr(model, "model", None)
        if isinstance(model_name, str):
            if _is_litellm_model(model_name):
                if has_litellm_overrides:
                    _apply_litellm_config(agent, model_name, config)
            elif not _is_openai_model_name(model_name):
                logger.warning(
                    "Skipping client_config for agent '%s': custom model '%s' is not supported for "
                    "client override (only OpenAI models or 'litellm/' models are supported)",
                    agent.name,
                    model_name,
                )
            else:
                if client is None:
                    return
                agent.model = _build_openai_model_for_client(model_name, client)
                if _is_codex_base_url(str(client.base_url)):
                    _apply_codex_compatibility_model_settings(agent)
        else:
            logger.warning(
                f"Cannot apply client config to agent '{agent.name}': unsupported model type {type(model).__name__}"
            )
    else:
        logger.warning(
            f"Cannot apply client config to agent '{agent.name}': unsupported model type {type(model).__name__}"
        )


def _agent_uses_litellm(agent: Agent) -> bool:
    model = agent.model
    if isinstance(model, str):
        return _is_litellm_model(model)
    if isinstance(model, OpenAIResponsesModel | OpenAIChatCompletionsModel):
        return _is_litellm_model(model.model)
    if _LITELLM_AVAILABLE and LitellmModel is not None and isinstance(model, LitellmModel):
        return True
    if isinstance(model, Model):
        model_name = getattr(model, "model", None)
        return isinstance(model_name, str) and _is_litellm_model(model_name)
    return False


def _get_litellm_provider(model_name: str) -> str | None:
    """Extract provider name from a LiteLLM model string.

    Examples:
        "litellm/anthropic/claude-sonnet-4" -> "anthropic"
        "anthropic/claude-sonnet-4" -> "anthropic"
        "claude-sonnet-4" -> None
    """
    # Strip litellm/ prefix if present
    name = model_name[8:] if model_name.startswith("litellm/") else model_name

    # Provider is the first segment before /
    if "/" in name:
        return name.split("/")[0]
    return None


def _is_openai_based_litellm_provider(provider: str | None) -> bool:
    # LiteLLM treats openai-like providers differently; allow request api_key as a fallback there.
    # For non-OpenAI providers (anthropic/gemini/etc), prefer env unless litellm_keys is provided.
    return provider in {None, "openai", "azure", "azure_ai", "openai_compatible"}


def _is_local_litellm_provider(provider: str | None) -> bool:
    return provider in {"ollama", "ollama_chat", "lm_studio"}


def _resolve_litellm_api_key(
    model_name: str,
    config: ClientConfig,
    existing_api_key: str | None = None,
) -> str | None:
    provider = _get_litellm_provider(model_name)

    # Prefer provider-specific keys when provided.
    if config.litellm_keys:
        if provider:
            for key, value in config.litellm_keys.items():
                key_str = key.value if hasattr(key, "value") else str(key)
                if key_str == provider:
                    return value
        # Provider missing in litellm_keys:
        # - For openai-based providers, allow falling back to config.api_key.
        # - Otherwise keep existing (or env if None).
        if _is_openai_based_litellm_provider(provider):
            return config.api_key if config.api_key is not None else existing_api_key
        return existing_api_key

    # No litellm_keys provided: only use config.api_key for openai-based providers.
    if _is_openai_based_litellm_provider(provider):
        return config.api_key if config.api_key is not None else existing_api_key
    return existing_api_key


def _resolve_litellm_base_url(
    model_name: str,
    config: ClientConfig,
    existing_base_url: str | None = None,
) -> str | None:
    provider = _get_litellm_provider(model_name)

    if config.base_url is None:
        return existing_base_url

    # Preserve main's Codex browser-auth guard for non-OpenAI providers, while
    # still allowing explicit LiteLLM proxy base URLs such as Anthropic/Gemini gateways.
    if _is_codex_base_url(config.base_url) and not _is_openai_based_litellm_provider(provider):
        return existing_base_url

    return config.base_url


def _apply_litellm_config(agent: Agent, model_name: str, config: ClientConfig) -> None:
    """Apply config to a LiteLLM model by creating a new LitellmModel instance."""
    if not _LITELLM_AVAILABLE or LitellmModel is None:
        logger.warning(
            f"Cannot apply client config to agent '{agent.name}': LiteLLM model "
            f"('{model_name}') requires openai-agents[litellm] to be installed"
        )
        return

    actual_model = _normalize_litellm_model_name(model_name)

    api_key = _resolve_litellm_api_key(actual_model, config, existing_api_key=None)
    base_url = _resolve_litellm_base_url(actual_model, config, existing_base_url=None)

    agent.model = LitellmModel(
        model=actual_model,
        base_url=base_url,
        api_key=api_key,
    )

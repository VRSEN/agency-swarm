import os
from typing import Any

from agents.models._openai_shared import get_default_openai_client
from agents.models.multi_provider import MultiProvider
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.models.openai_provider import OpenAIProvider
from agents.models.openai_responses import OpenAIResponsesModel
from openai import AsyncOpenAI

CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"


def is_codex_base_url(value: str | None) -> bool:
    if not value:
        return False
    return value.rstrip("/") == CODEX_BASE_URL


def agent_uses_codex_browser_auth(agent: object, run_config_override: object | None = None) -> bool:
    """Return True when an agent's model input is headed to Codex browser auth."""
    override_model = getattr(run_config_override, "model", None)
    model = override_model if override_model is not None else getattr(agent, "model", None)
    if isinstance(model, OpenAIResponsesModel | OpenAIChatCompletionsModel):
        return _client_uses_codex(model._client)
    if isinstance(model, str):
        provider = getattr(run_config_override, "model_provider", None)
        provider_codex = _provider_uses_codex(provider, model)
        if provider_codex is not None:
            return provider_codex
        if not _is_openai_model_name(model):
            return False
        return _default_openai_route_uses_codex()
    return False


def rewrite_system_input_roles_for_codex(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return model input with system replay messages represented as developer messages."""
    rewritten: list[dict[str, Any]] = []
    for item in messages:
        if item.get("role") == "system":
            rewritten.append({**item, "role": "developer"})
            continue
        rewritten.append(item)
    return rewritten


def _client_uses_codex(client: AsyncOpenAI | None) -> bool:
    if client is None:
        return False
    return is_codex_base_url(str(client.base_url))


def _provider_uses_codex(provider: object | None, model: str) -> bool | None:
    if isinstance(provider, MultiProvider):
        routed_provider = _multi_provider_provider_for_model(provider, model)
        if routed_provider is None:
            return False
        routed_codex = _provider_uses_codex(routed_provider, model)
        if routed_codex is None and routed_provider is not provider.openai_provider:
            return False
        return routed_codex
    if provider is None:
        return None
    if not isinstance(provider, OpenAIProvider):
        return False
    if provider._client is not None:
        return _client_uses_codex(provider._client)
    default_client = get_default_openai_client()
    if default_client is not None:
        return _client_uses_codex(default_client)
    base_url = getattr(provider, "_stored_base_url", None)
    if isinstance(base_url, str):
        return is_codex_base_url(base_url)
    return is_codex_base_url(os.getenv("OPENAI_BASE_URL"))


def _default_openai_route_uses_codex() -> bool:
    default_client = get_default_openai_client()
    if default_client is not None:
        return _client_uses_codex(default_client)
    return is_codex_base_url(os.getenv("OPENAI_BASE_URL"))


def _multi_provider_provider_for_model(provider: MultiProvider, model: str) -> object | None:
    if "/" not in model:
        return provider.openai_provider
    prefix, _rest = model.split("/", 1)
    if provider.provider_map is not None:
        mapped = provider.provider_map.get_provider(prefix)
        if mapped is not None:
            return mapped
    if prefix in {"litellm", "any-llm"}:
        return None
    if prefix == "openai":
        return provider.openai_provider
    if getattr(provider, "_unknown_prefix_mode", None) == "model_id":
        return provider.openai_provider
    return None


def _is_openai_model_name(model: str) -> bool:
    if "/" not in model:
        return True
    prefix, _rest = model.split("/", 1)
    return prefix == "openai"

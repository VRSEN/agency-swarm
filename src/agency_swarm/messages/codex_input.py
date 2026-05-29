from typing import Any

from agents.models._openai_shared import get_default_openai_client
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
        if not _is_openai_model_name(model):
            return False
        provider = getattr(run_config_override, "model_provider", None)
        return _provider_uses_codex(provider) or _client_uses_codex(get_default_openai_client())
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


def _provider_uses_codex(provider: object | None) -> bool:
    if not isinstance(provider, OpenAIProvider):
        return False
    if _client_uses_codex(provider._client):
        return True
    base_url = getattr(provider, "_stored_base_url", None)
    return isinstance(base_url, str) and is_codex_base_url(base_url)


def _is_openai_model_name(model: str) -> bool:
    if "/" not in model:
        return True
    prefix, _rest = model.split("/", 1)
    return prefix == "openai"

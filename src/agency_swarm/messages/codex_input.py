from typing import Any

from agents.models._openai_shared import get_default_openai_client
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
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
        return _is_openai_model_name(model) and _client_uses_codex(get_default_openai_client())
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


def _is_openai_model_name(model: str) -> bool:
    if "/" not in model:
        return True
    prefix, _rest = model.split("/", 1)
    return prefix == "openai"

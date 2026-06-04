"""OpenRouter model helpers."""

import os
from typing import Any

from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL_PREFIX = "openrouter/"


def is_openrouter_model_name(model_name: str) -> bool:
    """Return whether the model name uses Agency Swarm's OpenRouter prefix."""
    return model_name.startswith(OPENROUTER_MODEL_PREFIX)


def strip_openrouter_prefix(model_name: str) -> str:
    """Return the OpenRouter provider/model id without the Agency Swarm prefix."""
    return model_name[len(OPENROUTER_MODEL_PREFIX) :] if is_openrouter_model_name(model_name) else model_name


def get_openrouter_model_name(model: object) -> str | None:
    """Return the original ``openrouter/...`` model alias from a wrapped model."""
    value = getattr(model, "_agency_swarm_openrouter_model_name", None)
    return value if isinstance(value, str) and is_openrouter_model_name(value) else None


def build_openrouter_chat_model(
    model_name: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    default_headers: dict[str, str] | None = None,
    openai_client: AsyncOpenAI | None = None,
) -> OpenAIChatCompletionsModel:
    """Build an OpenAI-compatible Chat Completions model for OpenRouter."""
    actual_model = strip_openrouter_prefix(model_name)
    client = openai_client
    if client is None:
        resolved_api_key = api_key or os.getenv(OPENROUTER_API_KEY_ENV)
        if not resolved_api_key:
            raise ValueError("OPENROUTER_API_KEY is required for openrouter/... models")
        client = AsyncOpenAI(
            api_key=resolved_api_key,
            base_url=base_url or OPENROUTER_BASE_URL,
            default_headers=default_headers,
        )
    model = OpenAIChatCompletionsModel(model=actual_model, openai_client=client)
    model._agency_swarm_openrouter_model_name = f"{OPENROUTER_MODEL_PREFIX}{actual_model}"  # type: ignore[attr-defined]
    model._agency_swarm_usage_model_name = f"{OPENROUTER_MODEL_PREFIX}{actual_model}"  # type: ignore[attr-defined]
    model._agency_swarm_default_model_name = _default_settings_model_name(actual_model)  # type: ignore[attr-defined]
    return model


def _default_settings_model_name(actual_model: str) -> str:
    if actual_model.startswith("openai/"):
        return actual_model.split("/", 1)[1]
    return actual_model


def is_openrouter_model(model: Any) -> bool:
    """Return whether a model object was built for OpenRouter."""
    return get_openrouter_model_name(model) is not None

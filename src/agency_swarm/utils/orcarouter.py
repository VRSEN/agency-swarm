"""OrcaRouter model helpers.

OrcaRouter is an OpenAI-compatible gateway (``https://api.orcarouter.ai/v1``).
Models are addressed with the ``orcarouter/<provider>/<model>`` prefix and are
served through the standard Agents SDK chat-completions model, so provider
reasoning fields arrive in the ordinary OpenAI shape and are normalized by the
SDK without gateway-specific wrappers.
"""

import os
from typing import Any

from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

ORCAROUTER_API_KEY_ENV = "ORCAROUTER_API_KEY"
ORCAROUTER_BASE_URL = "https://api.orcarouter.ai/v1"
ORCAROUTER_MODEL_PREFIX = "orcarouter/"

__all__ = [
    "ORCAROUTER_API_KEY_ENV",
    "ORCAROUTER_BASE_URL",
    "ORCAROUTER_MODEL_PREFIX",
    "OrcaRouterChatCompletionsModel",
    "build_orcarouter_chat_model",
    "get_orcarouter_model_name",
    "is_orcarouter_model",
    "is_orcarouter_model_name",
    "strip_orcarouter_prefix",
]


def is_orcarouter_model_name(model_name: str) -> bool:
    """Return whether the model name uses Agency Swarm's OrcaRouter prefix."""
    return model_name.startswith(ORCAROUTER_MODEL_PREFIX)


def strip_orcarouter_prefix(model_name: str) -> str:
    """Return the OrcaRouter provider/model id without the Agency Swarm prefix."""
    return model_name[len(ORCAROUTER_MODEL_PREFIX) :] if is_orcarouter_model_name(model_name) else model_name


def get_orcarouter_model_name(model: object) -> str | None:
    """Return the original ``orcarouter/...`` model alias from a wrapped model."""
    value = getattr(model, "_agency_swarm_orcarouter_model_name", None)
    return value if isinstance(value, str) and is_orcarouter_model_name(value) else None


class OrcaRouterChatCompletionsModel(OpenAIChatCompletionsModel):
    """OpenAI-compatible chat model backed by the OrcaRouter gateway."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)


def build_orcarouter_chat_model(
    model_name: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    default_headers: dict[str, str] | None = None,
    openai_client: AsyncOpenAI | None = None,
) -> OrcaRouterChatCompletionsModel:
    """Build an OpenAI-compatible Chat Completions model for OrcaRouter."""
    actual_model = strip_orcarouter_prefix(model_name)
    client = openai_client
    if client is None:
        resolved_api_key = api_key or os.getenv(ORCAROUTER_API_KEY_ENV)
        if not resolved_api_key:
            raise ValueError("ORCAROUTER_API_KEY is required for orcarouter/... models")
        client = AsyncOpenAI(
            api_key=resolved_api_key,
            base_url=base_url or ORCAROUTER_BASE_URL,
            default_headers=default_headers,
        )
    model = OrcaRouterChatCompletionsModel(
        model=actual_model,
        openai_client=client,
    )
    model._agency_swarm_orcarouter_model_name = f"{ORCAROUTER_MODEL_PREFIX}{actual_model}"  # type: ignore[attr-defined]
    model._agency_swarm_usage_model_name = f"{ORCAROUTER_MODEL_PREFIX}{actual_model}"  # type: ignore[attr-defined]
    model._agency_swarm_default_model_name = _default_settings_model_name(actual_model)  # type: ignore[attr-defined]
    return model


def _default_settings_model_name(actual_model: str) -> str:
    if actual_model.startswith("openai/"):
        return actual_model.split("/", 1)[1]
    return actual_model


def is_orcarouter_model(model: Any) -> bool:
    """Return whether a model object was built for OrcaRouter."""
    return get_orcarouter_model_name(model) is not None

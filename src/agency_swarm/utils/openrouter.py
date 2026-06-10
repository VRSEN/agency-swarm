"""OpenRouter model helpers."""

import os
from collections.abc import AsyncIterator
from typing import Any, cast

from agents.models.chatcmpl_converter import ShouldReplayReasoningContent
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from agency_swarm.utils.openrouter_reasoning import (
    _OPENROUTER_OUTPUT_DETAILS,
    _OPENROUTER_REPLAY_DETAILS,
    OPENROUTER_BASE_URL,
    OPENROUTER_ENCRYPTED_REASONING_PLACEHOLDER,
    OPENROUTER_MODEL_PREFIX,
    OPENROUTER_REASONING_DETAILS_KEY,
    _attach_openrouter_output_details,
    _details_from_reasoning_item,
    _normalize_openrouter_reasoning,
    _normalize_openrouter_reasoning_stream,
    _openrouter_replay_details,
    _OpenRouterClientProxy,
    _should_replay_openrouter_reasoning,
)

OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"

__all__ = [
    "OPENROUTER_API_KEY_ENV",
    "OPENROUTER_BASE_URL",
    "OPENROUTER_MODEL_PREFIX",
    "OPENROUTER_ENCRYPTED_REASONING_PLACEHOLDER",
    "OPENROUTER_REASONING_DETAILS_KEY",
    "OpenRouterChatCompletionsModel",
    "build_openrouter_chat_model",
    "get_openrouter_model_name",
    "is_openrouter_model",
    "is_openrouter_model_name",
    "strip_openrouter_prefix",
    "_OPENROUTER_REPLAY_DETAILS",
    "_details_from_reasoning_item",
    "_normalize_openrouter_reasoning_stream",
]


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


class OpenRouterChatCompletionsModel(OpenAIChatCompletionsModel):
    """OpenRouter chat model with provider reasoning normalized for Agents."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if kwargs.get("should_replay_reasoning_content") is None:
            kwargs["should_replay_reasoning_content"] = _should_replay_openrouter_reasoning
        super().__init__(*args, **kwargs)

    async def get_response(self, *args: Any, **kwargs: Any) -> Any:
        details: list[list[dict[str, object]]] = []
        token = _OPENROUTER_OUTPUT_DETAILS.set(details)
        try:
            response = await super().get_response(*args, **kwargs)
            _attach_openrouter_output_details(response.output, details)
            return response
        finally:
            _OPENROUTER_OUTPUT_DETAILS.reset(token)

    async def stream_response(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        details: list[list[dict[str, object]]] = []
        token = _OPENROUTER_OUTPUT_DETAILS.set(details)
        try:
            async for event in super().stream_response(*args, **kwargs):
                if getattr(event, "type", None) == "response.completed":
                    completed = cast(Any, event)
                    _attach_openrouter_output_details(completed.response.output, details)
                yield event
        finally:
            _OPENROUTER_OUTPUT_DETAILS.reset(token)

    async def _fetch_response(self, *args: Any, **kwargs: Any) -> Any:
        input_value = args[1] if len(args) > 1 else kwargs.get("input")
        token = _OPENROUTER_REPLAY_DETAILS.set(
            _openrouter_replay_details(
                input_value,
                model=str(self.model),
                base_url=str(self._client.base_url),
                should_replay=self.should_replay_reasoning_content,
            )
        )
        try:
            result = await super()._fetch_response(*args, **kwargs)
            if isinstance(result, ChatCompletion):
                details = _OPENROUTER_OUTPUT_DETAILS.get()
                if details is not None:
                    details[:] = _normalize_openrouter_reasoning(result)
                return result
            if isinstance(result, tuple):
                response, stream = result
                return response, _normalize_openrouter_reasoning_stream(stream)
            return result
        finally:
            _OPENROUTER_REPLAY_DETAILS.reset(token)

    def _get_client(self) -> Any:
        return _OpenRouterClientProxy(super()._get_client())


def build_openrouter_chat_model(
    model_name: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    default_headers: dict[str, str] | None = None,
    openai_client: AsyncOpenAI | None = None,
    should_replay_reasoning_content: ShouldReplayReasoningContent | None = None,
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
    model = OpenRouterChatCompletionsModel(
        model=actual_model,
        openai_client=client,
        should_replay_reasoning_content=should_replay_reasoning_content,
    )
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

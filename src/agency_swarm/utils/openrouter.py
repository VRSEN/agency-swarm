"""OpenRouter model helpers."""

import os
from collections.abc import AsyncIterator
from typing import Any, cast

from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk

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


class OpenRouterChatCompletionsModel(OpenAIChatCompletionsModel):
    """OpenRouter chat model with provider reasoning normalized for Agents."""

    async def _fetch_response(self, *args: Any, **kwargs: Any) -> Any:
        result = await super()._fetch_response(*args, **kwargs)
        if isinstance(result, ChatCompletion):
            _normalize_openrouter_reasoning(result)
            return result
        if isinstance(result, tuple):
            response, stream = result
            return response, _normalize_openrouter_reasoning_stream(stream)
        return result


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
    model = OpenRouterChatCompletionsModel(model=actual_model, openai_client=client)
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


def _normalize_openrouter_reasoning(response: ChatCompletion) -> None:
    for choice in response.choices:
        message = choice.message
        dynamic = cast(Any, message)
        summary = _openrouter_reasoning_summary(message)
        if summary and not _field(message, "reasoning_content"):
            dynamic.reasoning_content = summary

        blocks = _openrouter_reasoning_blocks(_field(message, "reasoning_details"))
        if blocks and not _field(message, "thinking_blocks"):
            dynamic.thinking_blocks = blocks


async def _normalize_openrouter_reasoning_stream(stream: AsyncIterator[Any]) -> AsyncIterator[Any]:
    signatures: list[str] = []
    async for chunk in stream:
        if isinstance(chunk, ChatCompletionChunk):
            _normalize_openrouter_reasoning_chunk(chunk, signatures)
        yield chunk


def _normalize_openrouter_reasoning_chunk(chunk: ChatCompletionChunk, signatures: list[str]) -> None:
    for choice in chunk.choices:
        delta = choice.delta
        dynamic = cast(Any, delta)
        details = _field(delta, "reasoning_details")
        summary = _reasoning_details_summary(details)
        if summary and not _field(delta, "reasoning_content"):
            dynamic.reasoning_content = summary

        text = _reasoning_details_text(details)
        if text and not _field(delta, "reasoning"):
            dynamic.reasoning = text

        signatures.extend(_openrouter_reasoning_signatures(details))
        if signatures and not _field(delta, "thinking_blocks"):
            dynamic.thinking_blocks = [{"signature": "\n".join(signatures)}]


def _openrouter_reasoning_summary(value: Any) -> str:
    reasoning = _field(value, "reasoning")
    if isinstance(reasoning, str):
        return reasoning
    if isinstance(reasoning, dict):
        return _first_text(reasoning, ("summary", "thinking", "text", "reasoning", "content"))
    details = _field(value, "reasoning_details")
    return _reasoning_details_summary(details) or _reasoning_details_text(details)


def _reasoning_details_summary(details: Any) -> str:
    if not isinstance(details, list):
        return ""
    return "".join(
        text for item in details if isinstance(item, dict) for text in [_first_text(item, ("summary",))] if text
    )


def _reasoning_details_text(details: Any) -> str:
    if not isinstance(details, list):
        return ""
    return "".join(
        text
        for item in details
        if isinstance(item, dict)
        for text in [_first_text(item, ("thinking", "text", "reasoning", "content"))]
        if text
    )


def _openrouter_reasoning_blocks(details: Any, *, include_text: bool = True) -> list[dict[str, str]]:
    if not isinstance(details, list):
        return []

    blocks: list[dict[str, str]] = []
    for item in details:
        if not isinstance(item, dict):
            continue
        text = _first_text(item, ("thinking", "text", "reasoning", "content")) if include_text else ""
        signature = _first_text(item, ("signature", "data", "encrypted_content"))
        block: dict[str, str] = {}
        if text:
            block["thinking"] = text
        if signature:
            block["signature"] = signature
        if block:
            blocks.append(block)
    return blocks


def _openrouter_reasoning_signatures(details: Any) -> list[str]:
    if not isinstance(details, list):
        return []
    return [
        signature
        for item in details
        if isinstance(item, dict)
        for signature in [_first_text(item, ("signature", "data", "encrypted_content"))]
        if signature
    ]


def _first_text(value: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        found = value.get(key)
        if isinstance(found, str):
            return found
    return ""


def _field(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        found = value.get(key)
        if found is not None:
            return found

    found = getattr(value, key, None)
    if found is not None:
        return found

    extra = getattr(value, "model_extra", None)
    if isinstance(extra, dict):
        found = extra.get(key)
        if found is not None:
            return found

    return None

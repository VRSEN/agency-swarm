"""OpenRouter model helpers."""

import os
from collections.abc import AsyncIterator
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, cast

from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk

OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL_PREFIX = "openrouter/"
OPENROUTER_ENCRYPTED_REASONING_PLACEHOLDER = "[REDACTED]"
OPENROUTER_REASONING_DETAILS_KEY = "openrouter_reasoning_details"
_OPENROUTER_OUTPUT_DETAILS: ContextVar[list[list[dict[str, object]]] | None] = ContextVar(
    "_OPENROUTER_OUTPUT_DETAILS",
    default=None,
)
_OPENROUTER_REPLAY_DETAILS: ContextVar[list[list[dict[str, object]]] | None] = ContextVar(
    "_OPENROUTER_REPLAY_DETAILS",
    default=None,
)


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
        token = _OPENROUTER_REPLAY_DETAILS.set(_openrouter_replay_details(input_value))
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


class _OpenRouterClientProxy:
    def __init__(self, client: Any) -> None:
        self._client = client
        self.chat = _OpenRouterChatProxy(client.chat)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class _OpenRouterChatProxy:
    def __init__(self, chat: Any) -> None:
        self._chat = chat
        self.completions = _OpenRouterCompletionsProxy(chat.completions)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._chat, name)


class _OpenRouterCompletionsProxy:
    def __init__(self, completions: Any) -> None:
        self._completions = completions

    async def create(self, **kwargs: Any) -> Any:
        replay = _OPENROUTER_REPLAY_DETAILS.get() or []
        if replay and isinstance(kwargs.get("messages"), list):
            kwargs = {**kwargs, "messages": deepcopy(kwargs["messages"])}
        _attach_openrouter_replay_details(
            kwargs.get("messages"),
            replay,
        )
        return await self._completions.create(**kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._completions, name)


def _normalize_openrouter_reasoning(response: ChatCompletion) -> list[list[dict[str, object]]]:
    if len(response.choices) > 1 and any(_has_openrouter_reasoning(choice.message) for choice in response.choices):
        raise ValueError("OpenRouter reasoning is only supported for single-choice chat completions")

    output_details: list[dict[str, object]] = []
    for index, choice in enumerate(response.choices):
        message = choice.message
        dynamic = cast(Any, message)
        details = _copy_reasoning_details(_field(message, "reasoning_details"))
        if index == 0:
            output_details = details

        summary = _openrouter_reasoning_summary(message)
        if summary and not _field(message, "reasoning_content"):
            dynamic.reasoning_content = summary

        blocks = _openrouter_reasoning_blocks(_field(message, "reasoning_details"))
        if blocks and not _field(message, "thinking_blocks"):
            dynamic.thinking_blocks = blocks
    return [output_details] if output_details else []


async def _normalize_openrouter_reasoning_stream(
    stream: AsyncIterator[Any],
) -> AsyncIterator[Any]:
    states: dict[int, _OpenRouterStreamState] = {}
    output = _OPENROUTER_OUTPUT_DETAILS.get()
    async for chunk in stream:
        if isinstance(chunk, ChatCompletionChunk):
            if len(chunk.choices) > 1 and any(_has_openrouter_reasoning(choice.delta) for choice in chunk.choices):
                raise ValueError("OpenRouter reasoning is only supported for single-choice chat completions")
            primary = chunk.choices[0].index if chunk.choices else None
            _normalize_openrouter_reasoning_chunk(chunk, states)
            state = states.get(primary) if primary is not None else None
            if output is not None and state is not None:
                output[:] = [state.output_details] if state.output_details else []
        yield chunk


@dataclass
class _OpenRouterStreamState:
    signatures: list[str] = field(default_factory=list)
    has_reasoning: bool = False
    output_details: list[dict[str, object]] = field(default_factory=list)


def _normalize_openrouter_reasoning_chunk(
    chunk: ChatCompletionChunk,
    states: dict[int, _OpenRouterStreamState],
) -> None:
    for choice in chunk.choices:
        state = states.setdefault(choice.index, _OpenRouterStreamState())
        delta = choice.delta
        dynamic = cast(Any, delta)
        details = _field(delta, "reasoning_details")
        if details:
            dynamic._agency_swarm_skip_reasoning_content_copy = True
        state.output_details.extend(_copy_reasoning_details(details))
        text = _reasoning_details_text(details)
        summary = _reasoning_details_summary(details)
        if not summary and not text and not state.has_reasoning:
            summary = _encrypted_reasoning_placeholder(details)

        if summary and not _field(delta, "reasoning_content"):
            dynamic.reasoning_content = summary

        if text and not _field(delta, "reasoning"):
            dynamic.reasoning = text

        state.signatures.extend(_openrouter_reasoning_signatures(details))
        if state.signatures and not _field(delta, "thinking_blocks"):
            dynamic.thinking_blocks = [{"signature": "\n".join(state.signatures)}]

        state.has_reasoning = state.has_reasoning or bool(summary or text)


def _has_openrouter_reasoning(value: Any) -> bool:
    return bool(
        _field(value, "reasoning")
        or _field(value, "reasoning_content")
        or _field(value, "reasoning_details")
        or _field(value, "thinking_blocks")
    )


def _openrouter_reasoning_summary(value: Any) -> str:
    content = _field(value, "reasoning_content")
    if isinstance(content, str):
        return content
    reasoning = _field(value, "reasoning")
    if isinstance(reasoning, str):
        return reasoning
    if isinstance(reasoning, dict):
        return _first_text(reasoning, ("summary", "thinking", "text", "reasoning", "content"))
    details = _field(value, "reasoning_details")
    return (
        _reasoning_details_summary(details)
        or _reasoning_details_text(details)
        or _reasoning_details_text(_field(value, "thinking_blocks"))
        or _encrypted_reasoning_placeholder(details)
    )


def _openrouter_replay_details(input_value: Any) -> list[list[dict[str, object]]]:
    if not isinstance(input_value, list):
        return []

    pending: list[dict[str, object]] | None = None
    replay: list[list[dict[str, object]]] = []
    for item in input_value:
        item_type = _field(item, "type")
        if item_type == "reasoning":
            pending = _original_reasoning_details(item) or _details_from_reasoning_item(item)
            continue
        if pending and _is_assistant_output_item(item):
            replay.append(pending)
            pending = None
    return replay


def _attach_openrouter_replay_details(messages: Any, replay: list[list[dict[str, object]]]) -> None:
    if not isinstance(messages, list) or not replay:
        return

    targets = [
        message
        for message in messages
        if isinstance(message, dict)
        and message.get("role") == "assistant"
        and "reasoning_details" not in message
    ]
    selected = targets[-len(replay) :]
    selected_replay = replay[-len(selected) :] if selected else []
    for message, details in zip(selected, selected_replay, strict=True):
        message["reasoning_details"] = details


def _is_assistant_output_item(item: Any) -> bool:
    item_type = _field(item, "type")
    if item_type in {"message", "function_call"}:
        return True
    return _field(item, "role") == "assistant"


def _attach_openrouter_output_details(output: Any, details: list[list[dict[str, object]]]) -> None:
    if not isinstance(output, list) or not details:
        return

    remaining = list(details)
    for item in output:
        if not remaining:
            return
        if _field(item, "type") != "reasoning":
            continue
        provider_data = _field(item, "provider_data")
        provider = dict(provider_data) if isinstance(provider_data, dict) else {}
        provider[OPENROUTER_REASONING_DETAILS_KEY] = _copy_reasoning_details(remaining.pop(0))
        dynamic = cast(Any, item)
        dynamic.provider_data = provider


def _original_reasoning_details(item: Any) -> list[dict[str, object]]:
    provider_data = _field(item, "provider_data")
    if not isinstance(provider_data, dict):
        return []
    return _copy_reasoning_details(provider_data.get(OPENROUTER_REASONING_DETAILS_KEY))


def _details_from_reasoning_item(item: Any) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    encrypted = _encrypted_parts(item)
    contents = _content_texts(_field(item, "content"))

    for summary in _summary_texts(item):
        if summary != OPENROUTER_ENCRYPTED_REASONING_PLACEHOLDER:
            details.append({"type": "reasoning.summary", "summary": summary})

    extra_count = max(0, len(encrypted) - len(contents))
    for value in encrypted[:extra_count]:
        details.append({"type": "reasoning.encrypted", "data": value})

    signatures = encrypted[extra_count:]
    for index, text in enumerate(contents):
        detail: dict[str, object] = {"type": "reasoning.text", "text": text}
        if index < len(signatures):
            detail["signature"] = signatures[index]
        details.append(detail)

    return details


def _copy_reasoning_details(details: Any) -> list[dict[str, object]]:
    if not isinstance(details, list):
        return []
    return [cast(dict[str, object], deepcopy(item)) for item in details if isinstance(item, dict)]


def _summary_texts(item: Any) -> list[str]:
    summary = _field(item, "summary")
    if not isinstance(summary, list):
        return []
    return [text for value in summary for text in [_first_text_from_any(value, ("text", "summary"))] if text]


def _content_texts(content: Any) -> list[str]:
    if not isinstance(content, list):
        return []
    return [
        text
        for value in content
        for text in [_first_text_from_any(value, ("text", "thinking", "reasoning", "content"))]
        if text
    ]


def _encrypted_parts(item: Any) -> list[str]:
    encrypted = _field(item, "encrypted_content")
    if not isinstance(encrypted, str):
        return []
    return [part for part in encrypted.split("\n") if part]


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


def _encrypted_reasoning_placeholder(details: Any) -> str:
    if _openrouter_reasoning_signatures(details):
        return OPENROUTER_ENCRYPTED_REASONING_PLACEHOLDER
    return ""


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


def _first_text_from_any(value: Any, keys: tuple[str, ...]) -> str:
    if isinstance(value, dict):
        return _first_text(value, keys)
    for key in keys:
        found = getattr(value, key, None)
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

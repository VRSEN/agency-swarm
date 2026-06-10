"""OpenRouter reasoning normalization helpers."""

from collections.abc import AsyncIterator
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, cast

from agents.models.chatcmpl_converter import (
    ReasoningContentReplayContext,
    ReasoningContentSource,
    ShouldReplayReasoningContent,
)
from openai.types.chat import ChatCompletion, ChatCompletionChunk

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


def _should_replay_openrouter_reasoning(context: ReasoningContentReplayContext) -> bool:
    origin = context.reasoning.origin_model
    return (
        _is_openrouter_base_url(context.base_url)
        and origin is not None
        and _normalized_model(origin) == _normalized_model(context.model)
    )


def _is_openrouter_base_url(base_url: str | None) -> bool:
    return base_url is not None and base_url.rstrip("/") == OPENROUTER_BASE_URL


def _normalized_model(model: str) -> str:
    name = model[len(OPENROUTER_MODEL_PREFIX) :] if model.startswith(OPENROUTER_MODEL_PREFIX) else model
    return name.lower()


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
        details = _openrouter_message_details(message)
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
    has_summary: bool = False
    has_text: bool = False
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
        state.output_details.extend(_openrouter_message_details(delta))
        text = _reasoning_details_text(details)
        summary = _reasoning_details_summary(details)
        if not summary and not text and not state.has_reasoning:
            summary = _encrypted_reasoning_placeholder(details)

        if summary and not _field(delta, "reasoning_content"):
            dynamic.reasoning_content = _stream_reasoning_fragment(summary, state.has_summary)
            state.has_summary = True

        if text and not summary and not state.has_reasoning and not _field(delta, "reasoning_content"):
            dynamic.reasoning_content = _stream_reasoning_fragment(text, state.has_summary)
            state.has_summary = True

        if text and not _field(delta, "reasoning"):
            dynamic.reasoning = _stream_reasoning_fragment(text, state.has_text)
            state.has_text = True

        state.signatures.extend(_openrouter_reasoning_signatures(details))
        if state.signatures and not _field(delta, "thinking_blocks"):
            dynamic.thinking_blocks = [{"signature": "\n".join(state.signatures)}]

        state.has_reasoning = state.has_reasoning or bool(summary or text)


def _stream_reasoning_fragment(value: str, has_previous: bool) -> str:
    return f"\n{value}" if has_previous else value


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


def _openrouter_replay_details(
    input_value: Any,
    *,
    model: str,
    base_url: str | None,
    should_replay: ShouldReplayReasoningContent | None,
) -> list[list[dict[str, object]]]:
    if not isinstance(input_value, list):
        return []

    pending: list[dict[str, object]] | None = None
    replay: list[list[dict[str, object]]] = []
    for item in input_value:
        item_type = _field(item, "type")
        if item_type == "reasoning":
            details = _original_reasoning_details(item) or _details_from_reasoning_item(item)
            pending = (
                details if details and _should_replay_openrouter_item(item, model, base_url, should_replay) else None
            )
            continue
        if _is_assistant_output_item(item):
            replay.append(pending or [])
            pending = None
            continue
        pending = None
    return replay if any(replay) else []


def _attach_openrouter_replay_details(messages: Any, replay: list[list[dict[str, object]]]) -> None:
    if not isinstance(messages, list) or not replay:
        return

    targets = [
        message
        for message in messages
        if isinstance(message, dict) and message.get("role") == "assistant" and "reasoning_details" not in message
    ]
    if len(replay) != len(targets) and all(replay):
        targets = targets[-len(replay) :]
        replay = replay[-len(targets) :] if targets else []

    for message, details in zip(targets, replay, strict=False):
        if details:
            message["reasoning_details"] = details


def _is_assistant_output_item(item: Any) -> bool:
    item_type = _field(item, "type")
    if item_type in {"message", "function_call"}:
        return True
    return _field(item, "role") == "assistant"


def _should_replay_openrouter_item(
    item: Any,
    model: str,
    base_url: str | None,
    should_replay: ShouldReplayReasoningContent | None,
) -> bool:
    provider_data = _field(item, "provider_data")
    provider = provider_data if isinstance(provider_data, dict) else {}
    origin = provider.get("model")
    context = ReasoningContentReplayContext(
        model=model,
        base_url=base_url.rstrip("/") if base_url is not None else None,
        reasoning=ReasoningContentSource(
            item=item,
            origin_model=origin if isinstance(origin, str) else None,
            provider_data=provider,
        ),
    )
    if should_replay is not None:
        return should_replay(context)
    return False


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


def _openrouter_message_details(value: Any) -> list[dict[str, object]]:
    details = _copy_reasoning_details(_field(value, "reasoning_details"))
    if details:
        return details

    synthesized: list[dict[str, object]] = []
    summary = _field(value, "reasoning_content") or _openrouter_reasoning_summary(value)
    if isinstance(summary, str) and summary:
        synthesized.append({"type": "reasoning.summary", "summary": summary})

    for block in _openrouter_reasoning_blocks(_field(value, "thinking_blocks")):
        text = block.get("thinking")
        signature = block.get("signature")
        if text:
            detail: dict[str, object] = {"type": "reasoning.text", "text": text}
            if signature:
                detail["signature"] = signature
            synthesized.append(detail)
        elif signature:
            synthesized.append({"type": "reasoning.encrypted", "data": signature})
    return synthesized


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
    return "\n".join(
        text for item in details if isinstance(item, dict) for text in [_first_text(item, ("summary",))] if text
    )


def _reasoning_details_text(details: Any) -> str:
    if not isinstance(details, list):
        return ""
    return "\n".join(
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

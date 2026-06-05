from __future__ import annotations

from collections.abc import AsyncIterator
from inspect import signature
from typing import Any


def patch_litellm_thinking_blocks() -> None:
    """Expose LiteLLM thinking blocks as reasoning deltas for the Agents stream adapter."""
    try:
        from agents.extensions.models.litellm_model import ChatCmplStreamHandler
    except ImportError:
        return

    handler_cls: Any = ChatCmplStreamHandler
    if getattr(handler_cls, "_agency_swarm_thinking_patch", False):
        return

    original = handler_cls.handle_stream.__func__
    forwards_strict_feature_validation = "strict_feature_validation" in signature(original).parameters

    async def handle_stream(
        cls,
        response: Any,
        stream: AsyncIterator[Any],
        model: str | None = None,
        strict_feature_validation: bool = False,
    ) -> AsyncIterator[Any]:
        async def normalized_stream() -> AsyncIterator[Any]:
            async for chunk in stream:
                _copy_thinking_blocks_to_reasoning_content(chunk)
                yield chunk

        kwargs = {"strict_feature_validation": strict_feature_validation} if forwards_strict_feature_validation else {}
        async for event in original(cls, response, normalized_stream(), model, **kwargs):
            yield event

    handler_cls.handle_stream = classmethod(handle_stream)
    handler_cls._agency_swarm_thinking_patch = True


def _copy_thinking_blocks_to_reasoning_content(chunk: Any) -> None:
    choices = getattr(chunk, "choices", None)
    if not choices:
        return

    for choice in choices:
        delta = getattr(choice, "delta", None)
        if delta is None:
            continue
        if getattr(delta, "reasoning_content", None):
            continue

        text = (
            _field(delta, "reasoning_content")
            or _field(delta, "reasoning")
            or _thinking_blocks_text(_field(delta, "thinking_blocks"))
        )
        if text:
            delta.reasoning_content = text


def _field(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        found = value.get(key)
        if found is not None:
            return found
    found = getattr(value, key, None)
    if found is not None:
        return found
    model_extra = getattr(value, "model_extra", None)
    if isinstance(model_extra, dict):
        found = model_extra.get(key)
        if found is not None:
            return found
    provider_specific_fields = getattr(value, "provider_specific_fields", None)
    if isinstance(provider_specific_fields, dict):
        found = provider_specific_fields.get(key)
        if found is not None:
            return found
        google_fields = provider_specific_fields.get("google")
        if isinstance(google_fields, dict):
            found = google_fields.get(key)
            if found is not None:
                return found
    extra_content = getattr(value, "extra_content", None)
    if isinstance(extra_content, dict):
        found = extra_content.get(key)
        if found is not None:
            return found
        google_fields = extra_content.get("google")
        if isinstance(google_fields, dict):
            found = google_fields.get(key)
            if found is not None:
                return found
    return None


def _thinking_blocks_text(blocks: Any) -> str:
    if not isinstance(blocks, list):
        return ""

    parts: list[str] = []
    for block in blocks:
        if isinstance(block, dict):
            text = block.get("thinking")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)

"""Codex backend compatibility shims for streamed responses."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from agents import ModelSettings, OpenAIResponsesModel

from agency_swarm import Agent
from agency_swarm.messages.response_input_sanitizer import ensure_store_false_reasoning_encrypted_content

# Keep the pre-split logger name so log records are unchanged.
logger = logging.getLogger("agency_swarm.integrations.fastapi_utils.endpoint_handlers")


class _CodexAsyncStream:
    """Async iterator wrapper that patches missing output items in ResponseCompletedEvent.

    Wraps the raw AsyncStream returned by _fetch_response so that items streamed
    via ResponseOutputItemDoneEvent but omitted from
    ResponseCompletedEvent.response.output are injected back before the agents
    SDK processes the completed response.
    """

    def __init__(self, stream):
        self._stream = stream
        self._iter = stream.__aiter__()
        self._output_items: list[_CodexStreamedOutputItem] = []
        self._output_order_by_key: dict[tuple[str | None, str | None, str | None], tuple[int, int]] = {}

    def __aiter__(self):
        return self

    async def __anext__(self):
        from openai.types.responses import (
            ResponseCompletedEvent,
            ResponseOutputItemDoneEvent,
        )

        chunk = await self._iter.__anext__()

        if isinstance(chunk, ResponseOutputItemDoneEvent):
            sort_key = _codex_output_sort_key(getattr(chunk, "output_index", None), len(self._output_items))
            self._output_items.append(_CodexStreamedOutputItem(item=chunk.item, sort_key=sort_key))
            self._output_order_by_key[_codex_output_item_key(chunk.item)] = sort_key
        elif isinstance(chunk, ResponseCompletedEvent) and self._output_items:
            existing = {_codex_output_item_key(item) for item in chunk.response.output}
            missing = [entry for entry in self._output_items if _codex_output_item_key(entry.item) not in existing]
            if missing:
                logger.debug(
                    "Codex: injecting %d missing completed output item(s): %s",
                    len(missing),
                    [getattr(entry.item, "type", None) for entry in missing],
                )
                patched = _merge_codex_completed_output(chunk.response.output, missing, self._output_order_by_key)
                try:
                    chunk.response.output = patched
                except Exception:
                    try:
                        object.__setattr__(chunk.response, "output", patched)
                    except Exception as e:
                        logger.warning("Codex: could not patch response.output: %s", e)

        return chunk

    def __getattr__(self, name: str):
        return getattr(self._stream, name)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, exc_tb) -> None:
        await self._stream.__aexit__(exc_type, exc, exc_tb)

    async def aclose(self) -> None:
        await self._iter.aclose()


@dataclass(frozen=True)
class _CodexStreamedOutputItem:
    item: Any
    sort_key: tuple[int, int]


def _codex_output_item_key(item: Any) -> tuple[str | None, str | None, str | None]:
    """Return a stable identity key for Codex streamed/completed output items."""
    item_type = getattr(item, "type", None)
    call_id = getattr(item, "call_id", None)
    if item_type == "function_call" and call_id is not None:
        return (item_type, None, call_id)

    return (
        item_type,
        getattr(item, "id", None),
        call_id,
    )


def _codex_output_sort_key(output_index: Any, stream_position: int) -> tuple[int, int]:
    if isinstance(output_index, bool):
        return (1, stream_position)
    if isinstance(output_index, int):
        return (0, output_index)
    return (1, stream_position)


def _merge_codex_completed_output(
    completed_output: Sequence[Any],
    missing: Sequence[_CodexStreamedOutputItem],
    output_order_by_key: dict[tuple[str | None, str | None, str | None], tuple[int, int]],
) -> list[Any]:
    entries: list[tuple[tuple[int, int], int, Any]] = []
    fallback_offset = len(output_order_by_key)

    for completed_index, item in enumerate(completed_output):
        sort_key = output_order_by_key.get(_codex_output_item_key(item), (1, fallback_offset + completed_index))
        entries.append((sort_key, completed_index, item))

    missing_offset = len(completed_output)
    for missing_index, entry in enumerate(missing):
        entries.append((entry.sort_key, missing_offset + missing_index, entry.item))

    return [item for _, _, item in sorted(entries)]


def _apply_codex_compatibility_model_settings(agent: Agent) -> None:
    """Strip unsupported Responses parameters for the Codex browser-auth backend.

    Patch the model's _fetch_response on the instance (not via subclass) to
    wrap the stream in _CodexAsyncStream, which injects any output items that
    the Codex endpoint streams via ResponseOutputItemDoneEvent but omits from
    ResponseCompletedEvent.response.output.
    """
    current: ModelSettings = getattr(agent, "model_settings", None) or ModelSettings()
    current.store = False
    current.truncation = None
    ensure_store_false_reasoning_encrypted_content(current)
    agent.model_settings = current

    model = agent.model
    if not isinstance(model, OpenAIResponsesModel):
        return
    if getattr(model, "_codex_stream_patched", False):
        return

    _model_ref = model

    async def _fetch_response_patched(*args, stream=False, **kwargs):
        result = await OpenAIResponsesModel._fetch_response(_model_ref, *args, stream=stream, **kwargs)
        if stream:
            return _CodexAsyncStream(result)
        return result

    model._fetch_response = _fetch_response_patched  # type: ignore[method-assign]
    model._codex_stream_patched = True  # type: ignore[attr-defined]

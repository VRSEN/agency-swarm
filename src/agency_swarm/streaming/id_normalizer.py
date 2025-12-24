from __future__ import annotations

from collections import deque
from typing import Any

from agents import TResponseInputItem
from agents.models.fake_id import FAKE_RESPONSES_ID
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent, StreamEvent
from pydantic import BaseModel


class StreamIdNormalizer:
    """Normalize LiteLLM/Chat Completions placeholder IDs.

    The Agents SDK uses `FAKE_RESPONSES_ID="__fake_id__"` for Responses-style objects produced
    from non-Responses APIs (Chat Completions, LiteLLM). That placeholder is reused across many
    distinct output items, which breaks consumers that key by item_id / id.

    Design constraints:
    - Deterministic within a run: repeated deltas for the same output_index map to one stable id.
    - Tool calls use `call_id` for stable correlation.
    """

    def __init__(self) -> None:
        self._seq_by_agent_run_id: dict[str, int] = {}
        self._id_by_run_and_output_index: dict[tuple[str, int], str] = {}
        self._call_id_by_run_and_output_index: dict[tuple[str, int], str] = {}
        self._pending_ids_by_run_and_kind: dict[tuple[str, str], deque[str]] = {}
        self._unmatched_output_indices_by_run_and_kind: dict[tuple[str, str], deque[int]] = {}

    def normalize_stream_event(self, event: StreamEvent | dict[str, Any]) -> StreamEvent | dict[str, Any]:
        """Normalize a StreamEvent in-place and return it."""
        if isinstance(event, dict):
            return event

        if isinstance(event, RunItemStreamEvent):
            return self._normalize_run_item_stream_event(event)
        if not isinstance(event, RawResponsesStreamEvent):
            return event

        event_any: Any = event
        data = event.data
        if not isinstance(data, BaseModel):
            return event

        agent_run_id = self._coerce_agent_run_id(getattr(event, "agent_run_id", None))
        if agent_run_id is None:
            return event

        data_type = getattr(data, "type", None)
        output_index = self._coerce_output_index(getattr(data, "output_index", None))
        if output_index is None:
            return event
        kind = self._kind_for_raw_event(data_type, data=data)

        # Track tool call ids by output_index so argument deltas can be rewritten.
        if data_type in {"response.output_item.added", "response.output_item.done"}:
            item = getattr(data, "item", None)
            if isinstance(item, BaseModel) and getattr(item, "id", None) == FAKE_RESPONSES_ID:
                call_id = getattr(item, "call_id", None)
                if isinstance(call_id, str) and call_id and call_id != FAKE_RESPONSES_ID:
                    self._call_id_by_run_and_output_index[(agent_run_id, output_index)] = call_id
                    stable_id = call_id
                else:
                    stable_id, from_pending, created_new = self._get_or_create_stable_id(
                        agent_run_id, output_index, kind=kind
                    )
                    if created_new and kind in {"message", "reasoning"}:
                        self._unmatched_output_indices_by_run_and_kind.setdefault((agent_run_id, kind), deque()).append(
                            output_index
                        )

                self._id_by_run_and_output_index[(agent_run_id, output_index)] = stable_id

                item_copy = item.model_copy(update={"id": stable_id})
                data_copy = data.model_copy(update={"item": item_copy})
                event.data = data_copy
                # Keep root-level convenience attributes consistent if present.
                event_any.item_id = stable_id
                if getattr(event, "call_id", None) == FAKE_RESPONSES_ID:
                    event_any.call_id = stable_id
                return event

        # Rewrite any raw event that references item_id (most ChatCmpl/LiteLLM events do).
        item_id_value = getattr(data, "item_id", None)
        if item_id_value != FAKE_RESPONSES_ID:
            return event

        stable_item_id, _from_pending, created_new = self._resolve_item_id(
            agent_run_id, output_index, data_type, kind=kind
        )
        if stable_item_id == FAKE_RESPONSES_ID:
            return event

        if created_new and kind in {"message", "reasoning"}:
            self._unmatched_output_indices_by_run_and_kind.setdefault((agent_run_id, kind), deque()).append(
                output_index
            )

        data_copy = data.model_copy(update={"item_id": stable_item_id})
        event.data = data_copy
        event_any.item_id = stable_item_id
        return event

    def _normalize_run_item_stream_event(self, event: RunItemStreamEvent) -> RunItemStreamEvent:
        agent_run_id = self._coerce_agent_run_id(getattr(event, "agent_run_id", None))
        if agent_run_id is None:
            return event

        item = event.item
        if item is None:
            return event
        raw_item = getattr(item, "raw_item", None)
        if not isinstance(raw_item, BaseModel):
            return event

        raw_id = getattr(raw_item, "id", None)
        if raw_id != FAKE_RESPONSES_ID:
            return event

        name = event.name
        if name == "message_output_created":
            kind = "message"
        elif name == "reasoning_item_created":
            kind = "reasoning"
        elif name in {"tool_called", "tool_output", "handoff_requested", "handoff_occured"}:
            kind = "tool"
        else:
            return event

        stable_id: str | None = None
        if kind == "tool":
            call_id = getattr(raw_item, "call_id", None)
            if isinstance(call_id, str) and call_id and call_id != FAKE_RESPONSES_ID:
                stable_id = call_id

        if stable_id is None:
            stable_id = self._match_or_allocate_id_for_run_item(agent_run_id, kind=kind)
            if stable_id is None:
                return event

        raw_copy = raw_item.model_copy(update={"id": stable_id})
        item_any: Any = item
        item_any.raw_item = raw_copy
        event_any: Any = event
        event_any.item_id = stable_id
        if getattr(event, "call_id", None) == FAKE_RESPONSES_ID:
            event_any.call_id = stable_id
        return event

    def normalize_message_dicts(self, messages: list[TResponseInputItem]) -> list[TResponseInputItem]:
        """Rewrite placeholder ids in serialized message items.

        This is used both for API payloads (`new_messages`) and for normalizing messages before
        persistence when the upstream model supplies placeholder IDs.
        """
        seq_by_agent_run_id: dict[str, int] = {}
        normalized: list[TResponseInputItem] = []
        for idx, msg in enumerate(messages):
            msg_id = msg.get("id")
            if msg_id != FAKE_RESPONSES_ID:
                normalized.append(msg)
                continue

            msg_copy: Any = dict(msg)

            call_id = msg_copy.get("call_id")
            if isinstance(call_id, str) and call_id and call_id != FAKE_RESPONSES_ID:
                msg_copy["id"] = call_id
                normalized.append(msg_copy)
                continue

            agent_run_id = msg_copy.get("agent_run_id")
            if isinstance(agent_run_id, str) and agent_run_id:
                seq = seq_by_agent_run_id.get(agent_run_id, 0)
                seq_by_agent_run_id[agent_run_id] = seq + 1
                msg_copy["id"] = f"msg_{agent_run_id}_{seq}"
                normalized.append(msg_copy)
                continue

            msg_copy["id"] = f"msg_{idx}"
            normalized.append(msg_copy)

        return normalized

    def _resolve_item_id(
        self, agent_run_id: str, output_index: int, data_type: Any, *, kind: str | None
    ) -> tuple[str, bool, bool]:
        if data_type == "response.function_call_arguments.delta":
            call_id = self._call_id_by_run_and_output_index.get((agent_run_id, output_index))
            if call_id is not None:
                return call_id, False, False

        stable_id, from_pending, created_new = self._get_or_create_stable_id(agent_run_id, output_index, kind=kind)
        self._id_by_run_and_output_index[(agent_run_id, output_index)] = stable_id
        return stable_id, from_pending, created_new

    def _get_or_create_stable_id(
        self, agent_run_id: str, output_index: int, *, kind: str | None
    ) -> tuple[str, bool, bool]:
        existing = self._id_by_run_and_output_index.get((agent_run_id, output_index))
        if existing is not None:
            return existing, False, False

        if kind in {"message", "reasoning"}:
            pending = self._pending_ids_by_run_and_kind.get((agent_run_id, kind))
            if pending:
                return pending.popleft(), True, False

        return self._get_or_create_id(agent_run_id, output_index), False, True

    def _match_or_allocate_id_for_run_item(self, agent_run_id: str, *, kind: str) -> str | None:
        if kind not in {"message", "reasoning"}:
            return None

        unmatched = self._unmatched_output_indices_by_run_and_kind.get((agent_run_id, kind))
        if unmatched:
            output_index = unmatched.popleft()
            return self._id_by_run_and_output_index.get((agent_run_id, output_index))

        stable_id = self._new_seq_id(agent_run_id)
        self._pending_ids_by_run_and_kind.setdefault((agent_run_id, kind), deque()).append(stable_id)
        return stable_id

    def _new_seq_id(self, agent_run_id: str) -> str:
        seq = self._seq_by_agent_run_id.get(agent_run_id, 0)
        self._seq_by_agent_run_id[agent_run_id] = seq + 1
        return f"msg_{agent_run_id}_{seq}"

    def _get_or_create_id(self, agent_run_id: str, output_index: int) -> str:
        existing = self._id_by_run_and_output_index.get((agent_run_id, output_index))
        if existing is not None:
            return existing
        seq = self._seq_by_agent_run_id.get(agent_run_id, 0)
        self._seq_by_agent_run_id[agent_run_id] = seq + 1
        stable_id = f"msg_{agent_run_id}_{seq}"
        self._id_by_run_and_output_index[(agent_run_id, output_index)] = stable_id
        return stable_id

    @staticmethod
    def _coerce_agent_run_id(value: Any) -> str | None:
        if isinstance(value, str) and value:
            return value
        return None

    @staticmethod
    def _coerce_output_index(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _kind_for_raw_event(data_type: Any, *, data: BaseModel) -> str | None:
        if not isinstance(data_type, str):
            return None
        if data_type == "response.function_call_arguments.delta":
            return "tool"
        if "reasoning" in data_type:
            return "reasoning"
        if data_type in {"response.output_item.added", "response.output_item.done"}:
            item = getattr(data, "item", None)
            item_type = getattr(item, "type", None) if isinstance(item, BaseModel) else None
            if item_type == "reasoning":
                return "reasoning"
            if item_type == "message":
                return "message"
            if isinstance(item_type, str) and item_type.endswith("_call"):
                return "tool"
        return "message"

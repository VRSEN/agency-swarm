from __future__ import annotations

from collections import defaultdict
from typing import Any

ProviderBaseKey = tuple[str, str, str]
ProviderKey = tuple[str, str, str, str]


class StreamDisplayEventFilter:
    """Filter duplicate provider snapshots from display streams without mutating events."""

    _DEDUP_MODEL_PREFIXES = ("gemini/", "xai/", "litellm/gemini/", "litellm/xai/")

    def __init__(self) -> None:
        self._provider_item_ids: set[str] = set()
        self._provider_key_by_item_id: dict[str, ProviderKey] = {}
        self._provider_keys_by_base_key: dict[ProviderBaseKey, set[ProviderKey]] = defaultdict(set)
        self._streamed_text_item_ids: set[str] = set()
        self._streamed_text_provider_keys: set[ProviderKey] = set()
        self._streamed_text_keys_by_base_key: dict[ProviderBaseKey, set[ProviderKey]] = defaultdict(set)
        self._streamed_reasoning_item_ids: set[str] = set()
        self._streamed_reasoning_provider_keys: set[ProviderKey] = set()
        self._streamed_reasoning_keys_by_base_key: dict[ProviderBaseKey, set[ProviderKey]] = defaultdict(set)

    def should_emit(self, event: Any) -> bool:
        """Return False when an event only repeats text already emitted as deltas."""
        event_type = getattr(event, "type", None)
        if event_type == "raw_response_event":
            return self._should_emit_raw_event(getattr(event, "data", None))
        if event_type == "run_item_stream_event":
            return self._should_emit_run_item_event(event)
        return True

    def _should_emit_raw_event(self, data: Any) -> bool:
        data_type = getattr(data, "type", None)
        item_id = getattr(data, "item_id", None)
        output_index = getattr(data, "output_index", None)

        if data_type == "response.output_item.added":
            item = getattr(data, "item", None)
            if self._is_dedup_provider_item(item):
                self._track_provider_item(item, output_index=output_index)
                return not (getattr(item, "type", None) == "reasoning" and self._has_summary_text(item))
            return True

        if data_type == "response.reasoning_summary_text.delta":
            if isinstance(item_id, str) and item_id in self._provider_item_ids:
                self._streamed_reasoning_item_ids.add(item_id)
                provider_key = self._provider_key_by_item_id.get(item_id)
                if provider_key is not None:
                    self._streamed_reasoning_provider_keys.add(provider_key)
                    self._streamed_reasoning_keys_by_base_key[self._base_key_from_key(provider_key)].add(provider_key)
            return True

        if data_type == "response.output_text.delta":
            if isinstance(item_id, str) and item_id in self._provider_item_ids:
                self._streamed_text_item_ids.add(item_id)
                provider_key = self._provider_key_by_item_id.get(item_id)
                if provider_key is not None:
                    self._streamed_text_provider_keys.add(provider_key)
                    self._streamed_text_keys_by_base_key[self._base_key_from_key(provider_key)].add(provider_key)
            return True

        if data_type == "response.reasoning_summary_part.done":
            return True

        if data_type == "response.content_part.done":
            return True

        if data_type == "response.output_item.done":
            item = getattr(data, "item", None)
            if self._is_dedup_provider_item(item):
                self._track_provider_item(item, output_index=output_index)
            return True

        if data_type == "response.completed":
            response = getattr(data, "response", None)
            output = getattr(response, "output", None)
            if isinstance(output, list):
                for item in output:
                    if self._is_dedup_provider_item(item):
                        self._track_provider_item(item)
            return True

        return True

    def _should_emit_run_item_event(self, event: Any) -> bool:
        item = getattr(event, "item", None)
        raw_item = getattr(item, "raw_item", None)
        if not self._is_dedup_provider_item(raw_item):
            return True

        self._track_provider_item(raw_item)
        if event.name == "reasoning_item_created":
            return not self.has_streamed_reasoning(raw_item)
        if event.name == "message_output_created":
            return not self.has_streamed_text(raw_item)
        return True

    def has_streamed_text(self, item: Any) -> bool:
        """Return True when provider text deltas already rendered this item."""
        item_id = self._field(item, "id")
        return (
            isinstance(item_id, str)
            and item_id in self._streamed_text_item_ids
            or self._has_streamed_provider_key(
                item,
                self._streamed_text_provider_keys,
                self._streamed_text_keys_by_base_key,
            )
        )

    def has_streamed_reasoning(self, item: Any) -> bool:
        """Return True when provider reasoning deltas already rendered this item."""
        item_id = self._field(item, "id")
        return (
            isinstance(item_id, str) and item_id in self._streamed_reasoning_item_ids
        ) or self._has_streamed_provider_key(
            item,
            self._streamed_reasoning_provider_keys,
            self._streamed_reasoning_keys_by_base_key,
        )

    def _is_duplicate_completed_item(self, item: Any) -> bool:
        if not self._is_dedup_provider_item(item):
            return False
        self._track_provider_item(item)
        item_type = getattr(item, "type", None)
        if item_type == "reasoning":
            return self.has_streamed_reasoning(item)
        if item_type == "message":
            return self.has_streamed_text(item)
        return False

    def _track_provider_item(self, item: Any, *, output_index: Any = None) -> None:
        item_id = self._field(item, "id")
        if isinstance(item_id, str) and item_id:
            self._provider_item_ids.add(item_id)
            provider_key = self._provider_key(item, output_index=output_index)
            if provider_key is not None:
                self._provider_key_by_item_id[item_id] = provider_key
                self._provider_keys_by_base_key[self._base_key_from_key(provider_key)].add(provider_key)

    def _is_dedup_provider_item(self, item: Any) -> bool:
        provider_data = self._field(item, "provider_data")
        if not isinstance(provider_data, dict):
            return False
        model = provider_data.get("model")
        return isinstance(model, str) and model.startswith(self._DEDUP_MODEL_PREFIXES)

    def _provider_key(self, item: Any, *, output_index: Any = None) -> ProviderKey | None:
        provider_data = self._field(item, "provider_data")
        if not isinstance(provider_data, dict):
            return None
        model = provider_data.get("model")
        response_id = provider_data.get("response_id")
        item_type = self._field(item, "type")
        if not (isinstance(model, str) and isinstance(response_id, str) and isinstance(item_type, str)):
            return None
        discriminator = output_index
        if discriminator is None:
            discriminator = provider_data.get("output_index")
        if discriminator is None:
            item_id = self._field(item, "id")
            discriminator = f"id:{item_id}" if isinstance(item_id, str) and item_id else None
        if discriminator is not None:
            return (model, response_id, item_type, str(discriminator))
        return None

    @staticmethod
    def _base_key_from_key(provider_key: ProviderKey) -> ProviderBaseKey:
        return provider_key[:3]

    def _has_streamed_provider_key(
        self,
        item: Any,
        streamed_keys: set[ProviderKey],
        streamed_keys_by_base: dict[ProviderBaseKey, set[ProviderKey]],
    ) -> bool:
        provider_key = self._provider_key(item)
        if provider_key in streamed_keys:
            return True
        base_key = self._provider_base_key(item)
        if base_key is None:
            return False
        matching_keys = streamed_keys_by_base.get(base_key, set())
        return len(matching_keys) == 1

    def _provider_base_key(self, item: Any) -> ProviderBaseKey | None:
        provider_data = self._field(item, "provider_data")
        if not isinstance(provider_data, dict):
            return None
        model = provider_data.get("model")
        response_id = provider_data.get("response_id")
        item_type = self._field(item, "type")
        if isinstance(model, str) and isinstance(response_id, str) and isinstance(item_type, str):
            return (model, response_id, item_type)
        return None

    @staticmethod
    def _field(item: Any, name: str) -> Any:
        if isinstance(item, dict):
            return item.get(name)
        return getattr(item, name, None)

    @staticmethod
    def _has_summary_text(item: Any) -> bool:
        summary = getattr(item, "summary", None)
        if not isinstance(summary, list):
            return False
        for part in summary:
            text = getattr(part, "text", None)
            if isinstance(text, str) and text:
                return True
        return False

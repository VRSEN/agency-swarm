"""Responses input helpers for manual replay paths."""

from typing import Any, Literal, cast

from agents import TResponseInputItem

from agency_swarm.messages.message_filter import MessageFilter

REASONING_ENCRYPTED_CONTENT_INCLUDE: Literal["reasoning.encrypted_content"] = "reasoning.encrypted_content"
_RESPONSE_ONLY_REPLAY_KEYS = {"conversation_id", "previous_response_id", "response_id"}
_NESTED_CONTENT_TYPES_WITH_RESPONSE_IDS = {"output_text", "reasoning_text", "summary_text"}


def ensure_store_false_reasoning_encrypted_content(model_settings: Any) -> None:
    """Request encrypted reasoning when Responses history will not be stored server-side."""
    if getattr(model_settings, "store", None) is not False:
        return

    existing = list(getattr(model_settings, "response_include", None) or [])
    if REASONING_ENCRYPTED_CONTENT_INCLUDE not in existing:
        model_settings.response_include = [*existing, REASONING_ENCRYPTED_CONTENT_INCLUDE]


def sanitize_store_false_responses_input(history: list[Any]) -> list[dict[str, Any]]:
    """Drop reasoning items that cannot be replayed without server-side state."""
    sanitized: list[dict[str, Any]] = []
    dropped_item_ids: set[str] = set()
    dropping_legacy_response_span = False
    for msg in history:
        if dropping_legacy_response_span and _is_input_message(msg):
            dropping_legacy_response_span = False
        elif dropping_legacy_response_span:
            if isinstance(msg, dict) and isinstance(msg.get("id"), str):
                dropped_item_ids.add(msg["id"])
            continue
        if isinstance(msg, dict) and msg.get("type") == "reasoning" and not msg.get("encrypted_content"):
            _drop_previous_input_message(sanitized)
            if isinstance(msg.get("id"), str):
                dropped_item_ids.add(msg["id"])
            dropping_legacy_response_span = True
            continue
        if (
            isinstance(msg, dict)
            and msg.get("type") == "item_reference"
            and isinstance(msg.get("id"), str)
            and msg["id"] in dropped_item_ids
        ):
            continue
        cleaned = _sanitize_store_false_responses_value(msg, top_level=True)
        if isinstance(cleaned, dict):
            sanitized.append(cleaned)
    cleaned = MessageFilter.remove_orphaned_messages(cast(list[TResponseInputItem], sanitized))
    return cast(list[dict[str, Any]], cleaned)


def _drop_previous_input_message(messages: list[dict[str, Any]]) -> None:
    while messages:
        previous = messages[-1]
        if _is_input_message(previous):
            messages.pop()
            return
        if previous.get("type") == "reasoning":
            return
        messages.pop()


def _is_input_message(value: Any) -> bool:
    if not isinstance(value, dict):
        return False

    role = value.get("role")
    return role in {"user", "system", "developer"}


def _sanitize_store_false_responses_value(value: Any, *, top_level: bool = False) -> Any | None:
    if isinstance(value, list):
        cleaned_items: list[Any] = []
        for item in value:
            cleaned = _sanitize_store_false_responses_value(item)
            if cleaned is not None:
                cleaned_items.append(cleaned)
        return cleaned_items

    if not isinstance(value, dict):
        return value

    if value.get("type") == "reasoning" and not value.get("encrypted_content"):
        return None

    cleaned_dict: dict[str, Any] = {}
    for key, item in value.items():
        if key in _RESPONSE_ONLY_REPLAY_KEYS:
            continue
        if key == "id" and not top_level and value.get("type") in _NESTED_CONTENT_TYPES_WITH_RESPONSE_IDS:
            continue
        cleaned = _sanitize_store_false_responses_value(item)
        if cleaned is not None:
            cleaned_dict[key] = cleaned
    return cleaned_dict

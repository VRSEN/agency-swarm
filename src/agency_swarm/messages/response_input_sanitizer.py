"""Responses input helpers for manual replay paths."""

from typing import Any, Literal, cast

from agents import TResponseInputItem

from agency_swarm.messages.message_filter import MessageFilter

REASONING_ENCRYPTED_CONTENT_INCLUDE: Literal["reasoning.encrypted_content"] = "reasoning.encrypted_content"


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
    skip_next = False
    for msg in history:
        if skip_next:
            if isinstance(msg, dict) and isinstance(msg.get("id"), str):
                dropped_item_ids.add(msg["id"])
            skip_next = False
            continue
        if isinstance(msg, dict) and msg.get("type") == "reasoning" and not msg.get("encrypted_content"):
            if isinstance(msg.get("id"), str):
                dropped_item_ids.add(msg["id"])
            skip_next = True
            continue
        if (
            isinstance(msg, dict)
            and msg.get("type") == "item_reference"
            and isinstance(msg.get("id"), str)
            and msg["id"] in dropped_item_ids
        ):
            continue
        cleaned = _sanitize_store_false_responses_value(msg)
        if isinstance(cleaned, dict):
            sanitized.append(cleaned)
    cleaned = MessageFilter.remove_orphaned_messages(cast(list[TResponseInputItem], sanitized))
    return cast(list[dict[str, Any]], cleaned)


def _sanitize_store_false_responses_value(value: Any) -> Any | None:
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
        cleaned = _sanitize_store_false_responses_value(item)
        if cleaned is not None:
            cleaned_dict[key] = cleaned
    return cleaned_dict

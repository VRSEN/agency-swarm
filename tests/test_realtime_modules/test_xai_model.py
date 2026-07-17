"""Offline tests for the xAI realtime protocol-normalization adapter."""

import asyncio

import pytest
from agents.realtime import OpenAIRealtimeWebSocketModel

from agency_swarm.realtime.xai_model import XAIRealtimeWebSocketModel


def test_function_call_output_index_recovered_from_call_id_and_item_id() -> None:
    """Argument deltas missing output_index resolve via remembered call/item ids."""
    model = XAIRealtimeWebSocketModel()

    model._normalize_event(
        {
            "type": "response.output_item.added",
            "output_index": 2,
            "item": {"id": "item_7", "call_id": "call_9", "type": "function_call"},
        }
    )

    by_call = model._normalize_event({"type": "response.function_call_arguments.delta", "call_id": "call_9"})
    assert by_call["output_index"] == 2

    by_item = model._normalize_event({"type": "response.function_call_arguments.done", "item_id": "item_7"})
    assert by_item["output_index"] == 2


def test_function_call_output_index_cache_cleared_after_response_done() -> None:
    """Index fallbacks are response-scoped and reset when the response finalizes."""
    model = XAIRealtimeWebSocketModel()
    model._normalize_event(
        {
            "type": "response.output_item.added",
            "output_index": 3,
            "item": {"id": "item_1", "call_id": "call_1", "type": "function_call"},
        }
    )

    model._normalize_event({"type": "response.done", "response": {"output": []}})

    stale = model._normalize_event({"type": "response.function_call_arguments.delta", "call_id": "call_1"})
    assert stale["output_index"] == 0


def test_interrupt_response_restored_into_session_events() -> None:
    """xAI drops interrupt_response; the adapter restores the requested value."""
    model = XAIRealtimeWebSocketModel()
    model._remember_requested_interrupt_response({"turn_detection": {"interrupt_response": True}})

    normalized = model._normalize_event(
        {"type": "session.updated", "session": {"turn_detection": {"type": "server_vad"}}}
    )

    session = normalized["session"]
    assert session["turn_detection"]["interrupt_response"] is True
    assert session["audio"]["input"]["turn_detection"]["interrupt_response"] is True


def test_interrupt_response_remembered_from_session_update_event() -> None:
    """Outgoing session.update payloads refresh the remembered interrupt flag."""
    model = XAIRealtimeWebSocketModel()

    model._remember_requested_interrupt_response_from_event(
        {
            "type": "session.update",
            "session": {"audio": {"input": {"turn_detection": {"interrupt_response": False}}}},
        }
    )
    assert model._requested_interrupt_response is False

    model._remember_requested_interrupt_response_from_event(
        {"type": "session.update", "session": {"turn_detection": {"interrupt_response": True}}}
    )
    assert model._requested_interrupt_response is True


def test_transcription_usage_normalized_for_partial_payloads() -> None:
    """Missing or malformed usage becomes a valid tokens/duration payload."""
    normalize = XAIRealtimeWebSocketModel._normalize_transcription_usage

    assert normalize(None) == {"type": "tokens", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    assert normalize({"seconds": 1.5}) == {"type": "duration", "seconds": 1.5}

    tokens = normalize({"type": "tokens", "input_tokens": -3, "output_tokens": 4, "total_tokens": "bad"})
    assert tokens == {"type": "tokens", "input_tokens": 0, "output_tokens": 4, "total_tokens": 4}

    detailed = normalize({"input_tokens": 2, "input_token_details": {"audio_tokens": 1, "text_tokens": True}})
    assert detailed["input_token_details"] == {"audio_tokens": 1}


def test_current_item_cleared_during_transcription_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Transcription-completed handling suppresses conversation.item.retrieve sends."""
    model = XAIRealtimeWebSocketModel()
    model._current_item_id = "item_9"
    seen: dict[str, str | None] = {}

    async def capture(self: OpenAIRealtimeWebSocketModel, event: dict[str, object]) -> None:
        seen["during"] = self._current_item_id

    monkeypatch.setattr(OpenAIRealtimeWebSocketModel, "_handle_ws_event", capture)

    asyncio.run(
        model._handle_ws_event({"type": "conversation.item.input_audio_transcription.completed", "item_id": "item_9"})
    )

    assert seen["during"] is None
    assert model._current_item_id == "item_9"


def test_message_without_content_gets_role_fallback() -> None:
    """Messages missing a content list receive minimal role-appropriate content."""
    model = XAIRealtimeWebSocketModel()

    assistant = model._normalize_response_output_item({"type": "message", "role": "assistant"})
    assert assistant["content"] == [{"type": "output_text", "text": ""}]

    user = model._normalize_response_output_item({"type": "message", "role": "user"})
    assert user["content"] == [{"type": "input_text", "text": ""}]

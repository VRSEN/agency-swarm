from __future__ import annotations

from typing import Any


def history_with_encrypted_reasoning() -> list[dict[str, Any]]:
    return [
        {
            "type": "reasoning",
            "id": "rs_reasoning_123",
            "summary": [{"type": "summary_text", "text": "looked up the answer", "id": "rs_summary_123"}],
            "content": [{"type": "reasoning_text", "text": "private", "id": "rs_content_123"}],
            "encrypted_content": "encrypted_reasoning",
            "previous_response_id": "resp_previous_123",
            "status": "completed",
            "agent": "TestAgent",
            "callerAgent": None,
            "timestamp": 1,
        },
        {
            "type": "message",
            "role": "assistant",
            "id": "msg_answer_123",
            "content": [{"type": "output_text", "text": "The answer is 42.", "annotations": [], "id": "msg_text_123"}],
            "conversation_id": "conv_previous_123",
            "status": "completed",
            "agent": "TestAgent",
            "callerAgent": None,
            "timestamp": 2,
        },
        {
            "type": "function_call",
            "id": "fc_lookup_123",
            "call_id": "call_lookup_123",
            "name": "lookup",
            "arguments": "{}",
            "status": "completed",
            "agent": "TestAgent",
            "callerAgent": None,
            "timestamp": 3,
        },
        {
            "type": "function_call_output",
            "id": "fc_output_123",
            "call_id": "call_lookup_123",
            "output": "42",
            "status": "completed",
            "agent": "TestAgent",
            "callerAgent": None,
            "timestamp": 4,
        },
        {"type": "item_reference", "id": "msg_answer_123", "agent": "TestAgent", "callerAgent": None, "timestamp": 5},
    ]


def history_with_unencrypted_reasoning() -> list[dict[str, Any]]:
    history = history_with_encrypted_reasoning()
    reasoning = next(item for item in history if item.get("type") == "reasoning")
    reasoning.pop("encrypted_content")
    return history


def history_with_unencrypted_reasoning_before_tool_pair() -> list[dict[str, Any]]:
    return [
        {
            "type": "reasoning",
            "id": "rs_reasoning_123",
            "summary": [{"type": "summary_text", "text": "looked up the answer"}],
            "status": "completed",
        },
        {
            "type": "function_call",
            "id": "fc_lookup_123",
            "call_id": "call_lookup_123",
            "name": "lookup",
            "arguments": "{}",
            "status": "completed",
        },
        {
            "type": "function_call_output",
            "id": "fc_output_123",
            "call_id": "call_lookup_123",
            "output": "42",
            "status": "completed",
        },
        {"role": "user", "content": "again"},
    ]


def history_with_unencrypted_reasoning_before_current_user_message() -> list[dict[str, Any]]:
    return [
        {
            "type": "reasoning",
            "id": "rs_reasoning_123",
            "summary": [{"type": "summary_text", "text": "looked up the answer"}],
            "status": "completed",
        },
        {"role": "user", "content": "again"},
    ]


def history_with_unencrypted_reasoning_before_builtin_tool_call() -> list[dict[str, Any]]:
    return [
        {
            "type": "reasoning",
            "id": "rs_reasoning_123",
            "summary": [{"type": "summary_text", "text": "searched the web"}],
            "status": "completed",
        },
        {
            "type": "web_search_call",
            "id": "ws_lookup_123",
            "status": "completed",
        },
        {"role": "user", "content": "again"},
    ]


def history_with_unencrypted_reasoning_before_tool_search_pair() -> list[dict[str, Any]]:
    return [
        {
            "type": "reasoning",
            "id": "rs_reasoning_123",
            "summary": [{"type": "summary_text", "text": "searched local tools"}],
            "status": "completed",
        },
        {
            "type": "tool_search_call",
            "id": "ts_lookup_123",
            "call_id": "call_lookup_123",
            "arguments": {},
            "execution": "client",
        },
        {
            "type": "tool_search_output",
            "id": "ts_output_123",
            "call_id": "call_lookup_123",
            "tools": [],
            "execution": "client",
        },
        {"role": "user", "content": "again"},
    ]


def history_with_user_and_legacy_unencrypted_reasoning_turn() -> list[dict[str, Any]]:
    return [
        {"role": "user", "content": "what is 2+2?"},
        {
            "type": "reasoning",
            "id": "rs_reasoning_123",
            "summary": [{"type": "summary_text", "text": "calculated"}],
            "status": "completed",
        },
        {
            "type": "message",
            "role": "assistant",
            "id": "msg_answer_123",
            "content": [{"type": "output_text", "text": "4", "annotations": []}],
            "status": "completed",
        },
        {"role": "user", "content": "thanks"},
    ]

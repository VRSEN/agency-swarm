from __future__ import annotations

from agency_swarm.messages.response_input_sanitizer import sanitize_store_false_responses_input
from tests.response_history_samples import (
    history_with_encrypted_reasoning,
    history_with_unencrypted_reasoning_before_builtin_tool_call,
    history_with_unencrypted_reasoning_before_current_user_message,
    history_with_unencrypted_reasoning_before_tool_pair,
    history_with_unencrypted_reasoning_before_tool_search_pair,
    history_with_user_and_legacy_unencrypted_reasoning_turn,
)


def test_store_false_sanitizer_drops_dependent_followers_after_unencrypted_reasoning() -> None:
    sanitized = sanitize_store_false_responses_input(history_with_unencrypted_reasoning_before_tool_pair())

    assert sanitized == [{"role": "user", "content": "again"}]


def test_store_false_sanitizer_preserves_current_user_after_unencrypted_reasoning() -> None:
    sanitized = sanitize_store_false_responses_input(history_with_unencrypted_reasoning_before_current_user_message())

    assert sanitized == [{"role": "user", "content": "again"}]


def test_store_false_sanitizer_drops_builtin_tool_follower_after_unencrypted_reasoning() -> None:
    sanitized = sanitize_store_false_responses_input(history_with_unencrypted_reasoning_before_builtin_tool_call())

    assert sanitized == [{"role": "user", "content": "again"}]


def test_store_false_sanitizer_drops_tool_search_pair_after_unencrypted_reasoning() -> None:
    sanitized = sanitize_store_false_responses_input(history_with_unencrypted_reasoning_before_tool_search_pair())

    assert sanitized == [{"role": "user", "content": "again"}]


def test_store_false_sanitizer_drops_full_legacy_reasoning_turn() -> None:
    sanitized = sanitize_store_false_responses_input(history_with_user_and_legacy_unencrypted_reasoning_turn())

    assert sanitized == [{"role": "user", "content": "thanks"}]


def test_store_false_sanitizer_drops_late_reference_to_removed_reasoning() -> None:
    sanitized = sanitize_store_false_responses_input(
        [
            {
                "type": "reasoning",
                "id": "rs_reasoning_123",
                "summary": [{"type": "summary_text", "text": "legacy"}],
                "status": "completed",
            },
            {"role": "user", "content": "again"},
            {"type": "item_reference", "id": "rs_reasoning_123"},
        ]
    )

    assert sanitized == [{"role": "user", "content": "again"}]


def test_store_false_sanitizer_skips_non_messages_and_nested_unencrypted_reasoning() -> None:
    sanitized = sanitize_store_false_responses_input(
        [
            {
                "type": "reasoning",
                "id": "rs_reasoning_123",
                "summary": [{"type": "summary_text", "text": "legacy"}],
                "status": "completed",
            },
            "ignored legacy output",
            {
                "role": "user",
                "content": [
                    {"type": "reasoning", "summary": [{"type": "summary_text", "text": "nested"}]},
                    {"type": "input_text", "text": "again"},
                ],
            },
        ]
    )

    assert sanitized == [{"role": "user", "content": [{"type": "input_text", "text": "again"}]}]


def test_store_false_sanitizer_drops_prior_provider_outputs_before_legacy_reasoning() -> None:
    sanitized = sanitize_store_false_responses_input(
        [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "stale"}],
            },
            {
                "type": "reasoning",
                "id": "rs_reasoning_123",
                "summary": [{"type": "summary_text", "text": "legacy"}],
                "status": "completed",
            },
            {"role": "user", "content": "again"},
        ]
    )

    assert sanitized == [{"role": "user", "content": "again"}]


def test_store_false_sanitizer_keeps_prior_encrypted_reasoning_boundary() -> None:
    encrypted_reasoning = history_with_encrypted_reasoning()[0]
    sanitized = sanitize_store_false_responses_input(
        [
            encrypted_reasoning,
            {
                "type": "reasoning",
                "id": "rs_legacy_456",
                "summary": [{"type": "summary_text", "text": "legacy"}],
                "status": "completed",
            },
            {"role": "user", "content": "again"},
        ]
    )

    assert sanitized == [
        {
            "type": "reasoning",
            "id": "rs_reasoning_123",
            "summary": [{"type": "summary_text", "text": "looked up the answer"}],
            "content": [{"type": "reasoning_text", "text": "private"}],
            "encrypted_content": "encrypted_reasoning",
            "status": "completed",
            "agent": "TestAgent",
            "timestamp": 1,
        },
        {"role": "user", "content": "again"},
    ]

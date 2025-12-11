"""Regression tests for LiteLLM/Chat Completions placeholder IDs.

Bug: FastAPI streaming endpoints build the final `event: messages` payload by running
`MessageFilter.remove_duplicates()` on newly persisted items. When using LiteLLM/
Chat Completions models, many output items share `id=FAKE_RESPONSES_ID`, so the
final payload incorrectly dropped distinct items as "duplicates", making them
"disappear" after streaming.

This suite ensures `remove_duplicates` never de-dupes on the placeholder ID.
"""

from agents.models.fake_id import FAKE_RESPONSES_ID

from agency_swarm.messages.message_filter import MessageFilter


def test_remove_duplicates_does_not_drop_distinct_items_with_fake_id() -> None:
    messages = [
        {
            "id": FAKE_RESPONSES_ID,
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "reason 1"}],
        },
        {
            "id": FAKE_RESPONSES_ID,
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "hello"}],
        },
    ]

    result = MessageFilter.remove_duplicates(messages)

    assert result == messages


def test_remove_duplicates_still_dedupes_real_ids() -> None:
    messages = [
        {"id": "msg_1", "type": "message", "role": "assistant", "content": "A"},
        {"id": "msg_1", "type": "message", "role": "assistant", "content": "A"},
        {"id": "msg_2", "type": "message", "role": "assistant", "content": "B"},
    ]

    result = MessageFilter.remove_duplicates(messages)

    assert result == [messages[0], messages[2]]

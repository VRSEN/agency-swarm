"""Orphaned tool-search pairs must be stripped from replayable histories.

``remove_orphaned_messages`` keeps a call and its output together because the
Responses API rejects a history that carries one without the other. The
``tool_search_call`` / ``tool_search_output`` pair, emitted when a hosted
tool-search tool is used, was missing from the linking sets, so an orphaned
tool-search item survived the cleanup and would break replay.
"""

from agency_swarm.messages.message_filter import MessageFilter


def test_removes_tool_search_call_without_output() -> None:
    messages = [
        {"type": "message", "role": "user", "content": "hi"},
        {"type": "tool_search_call", "call_id": "ts_1", "arguments": "{}"},
    ]

    result = MessageFilter.remove_orphaned_messages(messages)

    assert result == [{"type": "message", "role": "user", "content": "hi"}]


def test_removes_tool_search_output_without_call() -> None:
    messages = [
        {"type": "tool_search_output", "call_id": "ts_1", "tools": []},
    ]

    result = MessageFilter.remove_orphaned_messages(messages)

    assert result == []


def test_keeps_matched_tool_search_pair() -> None:
    call = {"type": "tool_search_call", "call_id": "ts_1", "arguments": "{}"}
    output = {"type": "tool_search_output", "call_id": "ts_1", "tools": []}

    result = MessageFilter.remove_orphaned_messages([call, output])

    assert result == [call, output]


def test_removes_orphaned_agents_sdk_tool_search_items() -> None:
    messages = [
        {"type": "tool_search_call_item", "id": "ts_call_1"},
        {"type": "tool_search_output_item", "id": "ts_out_1"},
    ]

    result = MessageFilter.remove_orphaned_messages(messages)

    assert result == []


def test_keeps_matched_agents_sdk_tool_search_pair() -> None:
    call = {"type": "tool_search_call_item", "call_id": "ts_1"}
    output = {"type": "tool_search_output_item", "call_id": "ts_1"}

    result = MessageFilter.remove_orphaned_messages([call, output])

    assert result == [call, output]

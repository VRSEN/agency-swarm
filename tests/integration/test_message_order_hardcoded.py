import pytest

from agency_swarm.thread import ThreadManager


@pytest.mark.asyncio
async def test_hardcoded_message_order_preserved():
    """
    Human-readable, deterministic test.
    Given four messages appended in a specific order, the returned slice must
    preserve that exact order.
    """
    tm = ThreadManager()

    start = len(tm.get_all_messages())

    messages = [
        {
            "type": "message",
            "role": "assistant",
            "agent": "MainAgent",
            "callerAgent": None,
            "content": "ack",
            "timestamp": 1000,
        },
        {
            "type": "function_call",
            "agent": "MainAgent",
            "callerAgent": None,
            "function_call": {"name": "send_message", "arguments": "{}"},
            "timestamp": 1001,
        },
        {
            "type": "function_call_output",
            "agent": "MainAgent",
            "callerAgent": None,
            "output": "OK",
            "timestamp": 1002,
        },
        {
            "type": "message",
            "role": "assistant",
            "agent": "HelperAgent",
            "callerAgent": "MainAgent",
            "content": "OK",
            "timestamp": 1003,
        },
    ]

    tm.add_messages(messages)

    new_messages = tm.get_all_messages()[start:]
    got_types = [m.get("type") for m in new_messages]

    assert got_types == [
        "message",
        "function_call",
        "function_call_output",
        "message",
    ]

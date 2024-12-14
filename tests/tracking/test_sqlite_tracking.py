import json
from unittest.mock import MagicMock

import pytest
from openai.types.beta.threads.runs.run_step import Usage

from agency_swarm.util.tracking import SQLiteTracker


@pytest.fixture
def sqlite_tracker():
    tracker = SQLiteTracker(":memory:")
    yield tracker


def test_sqlite_track_and_get_total_tokens(sqlite_tracker):
    usage = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    sqlite_tracker.track_usage(
        usage, "test_assistant", "test_thread", "gpt-4o", "sender", "recipient"
    )
    totals = sqlite_tracker.get_total_tokens()
    assert totals == usage


def test_sqlite_multiple_entries(sqlite_tracker):
    # Insert multiple usage entries
    usages = [
        Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        Usage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
    ]
    for u in usages:
        sqlite_tracker.track_usage(
            u, "assistant", "thread", "gpt-4o", "sender", "recipient"
        )

    totals = sqlite_tracker.get_total_tokens()
    assert totals == Usage(prompt_tokens=30, completion_tokens=15, total_tokens=45)


def test_sqlite_track_assistant_message(sqlite_tracker):
    # Mock OpenAI client and responses
    mock_client = MagicMock()
    mock_message_log = MagicMock()
    mock_message_log.data = [
        MagicMock(role="user", content=[MagicMock(text=MagicMock(value="Hello"))]),
        MagicMock(
            role="assistant", content=[MagicMock(text=MagicMock(value="Hi there"))]
        ),
    ]
    mock_client.beta.threads.messages.list.return_value = mock_message_log

    mock_run = MagicMock()
    mock_run.model = "gpt-4o"
    mock_run.usage = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    mock_client.beta.threads.runs.retrieve.return_value = mock_run

    # Track a message
    sqlite_tracker.track_assistant_message(
        client=mock_client,
        thread_id="test_thread",
        run_id="test_run",
        message_content="Test response",
    )

    # Verify the message was stored
    cursor = sqlite_tracker.conn.cursor()
    cursor.execute("SELECT * FROM usage_tracking WHERE run_id = 'test_run'")
    row = cursor.fetchone()

    assert row is not None
    assert row[5] == "test_thread"  # thread_id
    assert row[6] == "test_run"  # run_id
    assert row[10] == "Test response"  # message_content

    # Verify input messages were stored as JSON
    input_messages = json.loads(row[11])  # input_messages
    assert len(input_messages) == 1
    assert input_messages[0]["role"] == "user"
    assert input_messages[0]["content"] == "Hello"

    assert row[7] == "gpt-4o"  # model
    assert row[1] == 10  # prompt_tokens
    assert row[2] == 5  # completion_tokens
    assert row[3] == 15  # total_tokens

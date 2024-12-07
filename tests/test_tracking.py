from unittest.mock import MagicMock, patch

import pytest
from openai.types.beta.threads.runs.run_step import Usage

from agency_swarm.util.tracking import LangfuseTracker, SQLiteTracker


@pytest.fixture
def sqlite_tracker():
    tracker = SQLiteTracker(":memory:")
    yield tracker


@pytest.fixture
def langfuse_tracker():
    tracker = LangfuseTracker()
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
    # Expected totals: prompt=30, completion=15, total=45
    assert totals == Usage(prompt_tokens=30, completion_tokens=15, total_tokens=45)


@patch("agency_swarm.util.tracking.langfuse_tracker.Langfuse")
def test_langfuse_track_usage(mock_langfuse, langfuse_tracker):
    # Create mock instance and set it as the client
    mock_langfuse_instance = MagicMock()
    mock_langfuse_instance.generation = MagicMock()
    mock_langfuse.return_value = mock_langfuse_instance
    langfuse_tracker.client = mock_langfuse_instance  # Set the mocked client

    usage = Usage(prompt_tokens=20, completion_tokens=10, total_tokens=30)

    langfuse_tracker.track_usage(
        usage=usage,
        assistant_id="test_assistant",
        thread_id="test_thread",
        model="gpt-4o",
        sender_agent_name="sender",
        recipient_agent_name="recipient",
    )

    mock_langfuse_instance.generation.assert_called_once_with(
        model="gpt-4o",
        metadata={
            "assistant_id": "test_assistant",
            "thread_id": "test_thread",
            "sender_agent_name": "sender",
            "recipient_agent_name": "recipient",
        },
        usage={
            "input": 20,
            "output": 10,
            "total": 30,
            "unit": "TOKENS",
        },
    )


@patch("agency_swarm.util.tracking.langfuse_tracker.Langfuse")
def test_langfuse_get_total_tokens_empty(mock_langfuse, langfuse_tracker):
    # Mock the fetch_observations method to return an empty list
    mock_langfuse_instance = MagicMock()
    mock_langfuse_instance.fetch_observations.return_value = MagicMock(data=[])
    mock_langfuse.return_value = mock_langfuse_instance
    langfuse_tracker.client = mock_langfuse_instance  # Set the mocked client

    totals = langfuse_tracker.get_total_tokens()
    assert totals == Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)


@patch("agency_swarm.util.tracking.langfuse_tracker.Langfuse")
def test_langfuse_get_total_tokens_multiple(mock_langfuse, langfuse_tracker):
    # Mock multiple generations
    mock_generation1 = MagicMock()
    mock_generation1.usage.input = 10
    mock_generation1.usage.output = 5
    mock_generation1.usage.total = 15

    mock_generation2 = MagicMock()
    mock_generation2.usage.input = 20
    mock_generation2.usage.output = 10
    mock_generation2.usage.total = 30

    mock_langfuse_instance = MagicMock()
    mock_langfuse_instance.fetch_observations.return_value = MagicMock(
        data=[mock_generation1, mock_generation2]
    )
    mock_langfuse.return_value = mock_langfuse_instance
    langfuse_tracker.client = mock_langfuse_instance  # Set the mocked client

    totals = langfuse_tracker.get_total_tokens()
    # Expected totals: prompt=30, completion=15, total=45
    assert totals == Usage(prompt_tokens=30, completion_tokens=15, total_tokens=45)


def test_get_observe_decorator(langfuse_tracker):
    assert callable(langfuse_tracker.get_observe_decorator())

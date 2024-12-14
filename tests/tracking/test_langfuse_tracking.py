from unittest.mock import MagicMock, patch

import pytest
from openai.types.beta.threads.runs.run_step import Usage

from agency_swarm.util.tracking import LangfuseTracker


@pytest.fixture
def langfuse_tracker():
    tracker = LangfuseTracker()
    yield tracker


@patch("agency_swarm.util.tracking.langfuse_tracker.Langfuse")
def test_langfuse_track_and_get_total_tokens(mock_langfuse, langfuse_tracker):
    # Create mock instance and set it as the client
    mock_langfuse_instance = MagicMock()
    mock_langfuse_instance.generation = MagicMock()
    mock_langfuse_instance.fetch_observations.return_value = MagicMock(
        data=[MagicMock(usage=MagicMock(input=10, output=5, total=15))]
    )
    mock_langfuse.return_value = mock_langfuse_instance
    langfuse_tracker.client = mock_langfuse_instance

    usage = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    langfuse_tracker.track_usage(
        usage=usage,
        assistant_id="test_assistant",
        thread_id="test_thread",
        model="gpt-4o",
        sender_agent_name="sender",
        recipient_agent_name="recipient",
    )

    totals = langfuse_tracker.get_total_tokens()
    assert totals == usage


@patch("agency_swarm.util.tracking.langfuse_tracker.Langfuse")
@patch("agency_swarm.util.tracking.langfuse_tracker.langfuse_context")
def test_langfuse_track_usage(mock_langfuse_context, mock_langfuse, langfuse_tracker):
    # Create mock instance and set it as the client
    mock_langfuse_instance = MagicMock()
    mock_langfuse_instance.generation = MagicMock()
    mock_langfuse.return_value = mock_langfuse_instance
    langfuse_tracker.client = mock_langfuse_instance

    # Mock context values
    mock_langfuse_context.get_current_trace_id.return_value = "test_trace"
    mock_langfuse_context.get_current_observation_id.return_value = "test_observation"

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
        trace_id="test_trace",
        parent_observation_id="test_observation",
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


@patch("agency_swarm.util.tracking.langfuse_tracker.langfuse_context")
def test_langfuse_track_assistant_message(mock_langfuse_context, langfuse_tracker):
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
    mock_run.model = "gpt-4o"  # Match the model name in the test
    mock_run.usage = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    mock_client.beta.threads.runs.retrieve.return_value = mock_run

    # Mock langfuse context
    mock_langfuse_context.client_instance = MagicMock()
    mock_langfuse_context.get_current_trace_id.return_value = "test_trace"
    mock_langfuse_context.get_current_observation_id.return_value = "test_observation"

    # Track a message
    langfuse_tracker.track_assistant_message(
        client=mock_client,
        thread_id="test_thread",
        run_id="test_run",
        message_content="Test response",
    )

    # Verify langfuse generation was called correctly
    mock_langfuse_context.client_instance.generation.assert_called_once_with(
        trace_id="test_trace",
        parent_observation_id="test_observation",
        model="gpt-4o",  # Match the model name
        usage=mock_run.usage,
        input=[{"role": "user", "content": "Hello"}],
        output="Test response",
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
    assert totals == Usage(prompt_tokens=30, completion_tokens=15, total_tokens=45)


def test_get_observe_decorator(langfuse_tracker):
    assert callable(langfuse_tracker.get_observe_decorator())

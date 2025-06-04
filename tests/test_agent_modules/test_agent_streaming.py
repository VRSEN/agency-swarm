from unittest.mock import MagicMock, patch

import pytest
from agents.lifecycle import RunHooks

from agency_swarm import Agent
from agency_swarm.thread import ThreadManager

# --- Streaming Tests ---


@pytest.mark.asyncio
async def test_get_response_stream_basic(tmp_path):
    agent = Agent(name="TestAgent", instructions="Test instructions")
    agent._thread_manager = ThreadManager()
    agent._agency_instance = type("Agency", (), {"agents": {"TestAgent": agent}, "user_context": {}})()
    message_content = "Stream this"

    async def dummy_stream():
        yield {"event": "text", "data": "Hello "}
        yield {"event": "text", "data": "World"}
        yield {"event": "done"}

    class DummyStreamedResult:
        def stream_events(self):
            return dummy_stream()

    with patch("agency_swarm.agent.Runner.run_streamed", return_value=DummyStreamedResult()):
        events = []
        async for event in agent.get_response_stream(message_content):
            events.append(event)
        assert events == [
            {"event": "text", "data": "Hello "},
            {"event": "text", "data": "World"},
            {"event": "done"},
        ]


@pytest.mark.asyncio
async def test_get_response_stream_final_result_processing(tmp_path):
    agent = Agent(name="TestAgent", instructions="Test instructions")
    agent._thread_manager = ThreadManager()
    agent._agency_instance = type("Agency", (), {"agents": {"TestAgent": agent}, "user_context": {}})()
    final_content = {"final_key": "final_value"}

    async def dummy_stream():
        yield {"event": "text", "data": "Thinking..."}
        yield {"event": "final_result", "data": final_content}
        yield {"event": "done"}

    class DummyStreamedResult:
        def stream_events(self):
            return dummy_stream()

    with patch("agency_swarm.agent.Runner.run_streamed", return_value=DummyStreamedResult()):
        events = []
        async for event in agent.get_response_stream("Process this"):
            events.append(event)
        assert events == [
            {"event": "text", "data": "Thinking..."},
            {"event": "final_result", "data": final_content},
            {"event": "done"},
        ]


@pytest.mark.asyncio
@patch("agency_swarm.agent.Runner.run_streamed")
async def test_get_response_stream_generates_thread_id(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    """Test that get_response_stream generates a consistent thread ID for user interactions."""

    async def mock_stream_wrapper():
        yield {"event": "text", "data": "Hello"}
        yield {"event": "done"}

    class MockStreamedResult:
        def stream_events(self):
            return mock_stream_wrapper()

    mock_runner_run_streamed_patch.return_value = MockStreamedResult()

    events = []
    async for event in minimal_agent.get_response_stream("Test message"):
        events.append(event)

    assert len(events) == 2
    # Verify that get_thread was called with the consistent user->agent format
    mock_thread_manager.get_thread.assert_called()
    call_args = mock_thread_manager.get_thread.call_args[0]
    assert len(call_args) == 1
    assert call_args[0] == "user->TestAgent"


@pytest.mark.asyncio
@patch("agency_swarm.agent.Runner.run_streamed")
async def test_get_response_stream_agent_to_agent_communication(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    """Test that get_response_stream works correctly for agent-to-agent communication."""

    async def mock_stream_wrapper():
        yield {"event": "text", "data": "Hello"}
        yield {"event": "done"}

    class MockStreamedResult:
        def stream_events(self):
            return mock_stream_wrapper()

    mock_runner_run_streamed_patch.return_value = MockStreamedResult()

    events = []
    async for event in minimal_agent.get_response_stream("Test message", sender_name="SomeAgent"):
        events.append(event)

    assert len(events) == 2
    # Verify that get_thread was called with the sender->recipient format
    mock_thread_manager.get_thread.assert_called_once()
    call_args = mock_thread_manager.get_thread.call_args[0]
    assert len(call_args) == 1
    # Should be in format "SomeAgent->TestAgent"
    assert call_args[0] == "SomeAgent->TestAgent"


@pytest.mark.asyncio
async def test_get_response_stream_input_validation_none_empty(minimal_agent, mock_thread_manager):
    """Test that get_response_stream validates input for None and empty messages."""
    # Test None message
    events = []
    async for event in minimal_agent.get_response_stream(None):
        events.append(event)
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "cannot be None" in events[0]["content"]

    # Test empty message
    events = []
    async for event in minimal_agent.get_response_stream("   "):
        events.append(event)
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "cannot be empty" in events[0]["content"]


@pytest.mark.asyncio
@patch("agency_swarm.agent.Runner.run_streamed")
async def test_get_response_stream_context_propagation(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    """Test that get_response_stream properly propagates context and hooks."""

    async def mock_stream_wrapper():
        yield {"event": "text", "data": "Hello"}
        yield {"event": "done"}

    class MockStreamedResult:
        def stream_events(self):
            return mock_stream_wrapper()

    mock_runner_run_streamed_patch.return_value = MockStreamedResult()

    context_override = {"test_key": "test_value"}
    hooks_override = MagicMock(spec=RunHooks)

    events = []
    async for event in minimal_agent.get_response_stream(
        "Test message", context_override=context_override, hooks_override=hooks_override
    ):
        events.append(event)

    assert len(events) == 2
    mock_runner_run_streamed_patch.assert_called_once()
    call_kwargs = mock_runner_run_streamed_patch.call_args[1]
    assert "context" in call_kwargs
    assert "hooks" in call_kwargs
    assert call_kwargs["hooks"] == hooks_override


@pytest.mark.asyncio
@patch("agency_swarm.agent.Runner.run_streamed")
async def test_get_response_stream_thread_management(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    """Test that get_response_stream properly manages thread state."""

    async def mock_stream_wrapper():
        yield {"event": "text", "data": "Hello"}
        yield {"event": "done"}

    class MockStreamedResult:
        def stream_events(self):
            return mock_stream_wrapper()

    mock_runner_run_streamed_patch.return_value = MockStreamedResult()

    events = []
    async for event in minimal_agent.get_response_stream("Test message"):
        events.append(event)

    assert len(events) == 2
    # Verify thread was retrieved with the consistent user->agent format
    mock_thread_manager.get_thread.assert_called_once()
    call_args = mock_thread_manager.get_thread.call_args[0]
    assert len(call_args) == 1
    # Should be the consistent user->agent format
    assert call_args[0] == "user->TestAgent"
    # Verify items were added to thread
    mock_thread_manager.add_items_and_save.assert_called()

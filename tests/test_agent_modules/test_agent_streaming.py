from unittest.mock import MagicMock, patch

import pytest
from agents.lifecycle import RunHooks

from agency_swarm import Agent

# --- Streaming Tests ---


@pytest.mark.asyncio
async def test_get_response_stream_basic():
    agent = Agent(name="TestAgent", instructions="Test instructions")
    message_content = "Stream this"

    async def dummy_stream():
        yield {"event": "text", "data": "Hello "}
        yield {"event": "text", "data": "World"}
        yield {"event": "done"}

    class DummyStreamedResult:
        def stream_events(self):
            return dummy_stream()

    with patch("agents.Runner.run_streamed", return_value=DummyStreamedResult()):
        events = []
        async for event in agent.get_response_stream(message_content):
            events.append(event)
        assert events == [
            {"event": "text", "data": "Hello ", "agent": "TestAgent", "callerAgent": None},
            {"event": "text", "data": "World", "agent": "TestAgent", "callerAgent": None},
            {"event": "done", "agent": "TestAgent", "callerAgent": None},
        ]


@pytest.mark.asyncio
async def test_get_response_stream_final_result_processing():
    agent = Agent(name="TestAgent", instructions="Test instructions")
    final_content = {"final_key": "final_value"}

    async def dummy_stream():
        yield {"event": "text", "data": "Thinking..."}
        yield {"event": "final_result", "data": final_content}
        yield {"event": "done"}

    class DummyStreamedResult:
        def stream_events(self):
            return dummy_stream()

    with patch("agents.Runner.run_streamed", return_value=DummyStreamedResult()):
        events = []
        async for event in agent.get_response_stream("Process this"):
            events.append(event)
        assert events == [
            {"event": "text", "data": "Thinking...", "agent": "TestAgent", "callerAgent": None},
            {"event": "final_result", "data": final_content, "agent": "TestAgent", "callerAgent": None},
            {"event": "done", "agent": "TestAgent", "callerAgent": None},
        ]


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_get_response_stream_agent_to_agent_communication(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    """Test that get_response_stream works correctly for agent-to-agent communication."""
    from agency_swarm.agent_core import AgencyContext

    async def mock_stream_wrapper():
        yield {"event": "text", "data": "Hello"}
        yield {"event": "done"}

    class MockStreamedResult:
        def stream_events(self):
            return mock_stream_wrapper()

    mock_runner_run_streamed_patch.return_value = MockStreamedResult()

    # Create agency context for agent-to-agent communication
    mock_agency = MagicMock()
    mock_agency.agents = {"SomeAgent": MagicMock(name="SomeAgent")}
    mock_agency.user_context = {}

    agency_context = AgencyContext(
        agency_instance=mock_agency,
        thread_manager=mock_thread_manager,
        subagents={},
        load_threads_callback=None,
        save_threads_callback=None,
        shared_instructions=None,
    )

    events = []
    async for event in minimal_agent.get_response_stream(
        "Test message", sender_name="SomeAgent", agency_context=agency_context
    ):
        events.append(event)

    assert len(events) == 2
    # Verify that messages were added with proper sender metadata
    mock_thread_manager.add_messages.assert_called()
    call_args = mock_thread_manager.add_messages.call_args[0]
    messages = call_args[0]
    assert len(messages) > 0
    for msg in messages:
        assert msg.get("agent") == "TestAgent"
        assert msg.get("callerAgent") == "SomeAgent"


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
@patch("agents.Runner.run_streamed")
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
@patch("agents.Runner.run_streamed")
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

    assert events == [
        {"event": "text", "data": "Hello", "agent": "TestAgent", "callerAgent": None},
        {"event": "done", "agent": "TestAgent", "callerAgent": None},
    ]

    # Verify messages were saved with proper metadata
    mock_thread_manager.add_messages.assert_called()
    call_args = mock_thread_manager.add_messages.call_args[0]
    messages = call_args[0]
    assert len(messages) > 0
    for msg in messages:
        assert msg.get("agent") == "TestAgent"
        assert msg.get("callerAgent") is None  # None for user messages

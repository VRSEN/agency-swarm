from unittest.mock import MagicMock, patch

import pytest
from agents.lifecycle import RunHooks

from agency_swarm import Agent

# --- Streaming Tests ---


@pytest.mark.asyncio
async def test_get_response_stream_basic():
    """Validate that streamed dict events are enriched with agent/callerAgent metadata.

    Why this matters: The UI and persistence layers consume these fields to attribute
    output to the correct agent (see docs/additional-features/streaming.mdx and
    docs/additional-features/observability.mdx). This test proves the need for
    metadata enrichment in the streaming path.
    """
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
    """Validate metadata presence for final_result events in streaming.

    Ensures downstream consumers can attribute final output to the right agent,
    per the documented metadata contract.
    """
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
async def test_get_response_stream_generates_thread_id(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    """Validate consistent thread grouping for user interactions.

    The grouping relies on metadata added during streaming; this test ensures
    we persist correctly attributed messages, which depends on enrichment paths.
    """

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
    # Verify that messages were added to the thread manager
    mock_thread_manager.add_messages.assert_called()
    # Messages should be saved with proper agent metadata
    call_args = mock_thread_manager.add_messages.call_args[0]
    messages = call_args[0]
    assert len(messages) > 0
    for msg in messages:
        assert msg.get("agent") == "TestAgent"


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_get_response_stream_agent_to_agent_communication(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    """Validate metadata for agent-to-agent streaming.

    Proves that sender/receiver attribution via agent/callerAgent is present,
    enabling downstream flows and UI to render correct attribution.
    """
    from agency_swarm.agent.core import AgencyContext

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

    assert len(events) == 2
    # Verify messages were saved with proper metadata
    mock_thread_manager.add_messages.assert_called()
    call_args = mock_thread_manager.add_messages.call_args[0]
    messages = call_args[0]
    assert len(messages) > 0
    for msg in messages:
        assert msg.get("agent") == "TestAgent"
        assert msg.get("callerAgent") is None  # None for user messages


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_stream_assigns_stable_agent_run_id_per_new_agent(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    """Ensure each new_agent event establishes a stable agent_run_id that is
    attached to all subsequent events and saved messages for that agent instance.
    """

    class Obj:
        pass

    def make_new_agent_event(agent_name: str, event_id: str):
        e = Obj()
        e.type = "agent_updated_stream_event"
        new_agent = Obj()
        new_agent.name = agent_name
        e.new_agent = new_agent
        e.id = event_id
        return e

    class DummyItem:
        def __init__(self, text: str):
            self.text = text

        def to_input_item(self):
            # Minimal assistant message dict compatible with storage
            return {"role": "assistant", "content": self.text, "id": f"msg_{self.text}"}

    def make_raw_response_item_event(item: DummyItem):
        e = Obj()
        e.type = "raw_response_event"
        e.item = item
        return e

    async def mock_stream_wrapper():
        # First agent instance
        yield make_new_agent_event("RiskAnalyst", "agent_updated_stream_event_AAAA")
        yield make_raw_response_item_event(DummyItem("A"))
        # Second agent instance of the same name
        yield make_new_agent_event("RiskAnalyst", "agent_updated_stream_event_BBBB")
        yield make_raw_response_item_event(DummyItem("B"))

    class MockStreamedResult:
        def stream_events(self):
            return mock_stream_wrapper()

    mock_runner_run_streamed_patch.return_value = MockStreamedResult()

    events = []
    async for event in minimal_agent.get_response_stream("Test message"):
        events.append(event)

    # Validate agent_run_id propagation on emitted events
    assert getattr(events[0], "type", None) == "agent_updated_stream_event"
    assert getattr(events[0], "agent_run_id", None) == "agent_updated_stream_event_AAAA"
    assert getattr(events[1], "type", None) == "raw_response_event"
    assert getattr(events[1], "agent_run_id", None) == "agent_updated_stream_event_AAAA"

    assert getattr(events[2], "type", None) == "agent_updated_stream_event"
    assert getattr(events[2], "agent_run_id", None) == "agent_updated_stream_event_BBBB"
    assert getattr(events[3], "type", None) == "raw_response_event"
    assert getattr(events[3], "agent_run_id", None) == "agent_updated_stream_event_BBBB"

    # Validate saved assistant messages include the correct agent_run_id grouping
    saved_batches = [call.args[0] for call in mock_thread_manager.add_messages.call_args_list]
    saved_msgs = [m for batch in saved_batches for m in batch]
    # Keep only assistant outputs created from stream items in this test
    saved_assistant = {m.get("id"): m for m in saved_msgs if isinstance(m, dict) and m.get("id", "").startswith("msg_")}
    assert set(saved_assistant.keys()) == {"msg_A", "msg_B"}
    assert saved_assistant["msg_A"]["agent_run_id"] == "agent_updated_stream_event_AAAA"
    assert saved_assistant["msg_B"]["agent_run_id"] == "agent_updated_stream_event_BBBB"

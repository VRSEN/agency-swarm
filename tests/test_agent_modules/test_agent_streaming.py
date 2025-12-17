from unittest.mock import MagicMock, patch

import pytest
from agents import RunConfig
from agents.agent import Agent as SDKAgent
from agents.items import MessageOutputItem
from agents.lifecycle import RunHooks
from agents.stream_events import (
    AgentUpdatedStreamEvent,
    RawResponsesStreamEvent,
    RunItemStreamEvent,
)
from openai.types.responses import ResponseOutputMessage, ResponseOutputText

from agency_swarm import Agency, Agent, StreamingRunResponse
from agency_swarm.agent.core import AgencyContext
from agency_swarm.agent.execution_stream_persistence import StreamMetadataStore, _persist_streamed_items
from agency_swarm.messages import MessageFormatter

# --- Streaming Tests ---


@pytest.mark.asyncio
async def test_get_response_stream_basic():
    """Validate that RunItemStreamEvent objects are enriched with agent/callerAgent metadata.

    Why this matters: The UI and persistence layers consume these fields to attribute
    output to the correct agent (see docs/additional-features/streaming.mdx and
    docs/additional-features/observability.mdx). This test proves metadata
    enrichment works for proper SDK events.
    """
    agent = Agent(name="TestAgent", instructions="Test instructions")
    message_content = "Stream this"

    # Create proper SDK event objects
    msg_item1 = MessageOutputItem(
        raw_item=ResponseOutputMessage(
            id="msg_1",
            content=[ResponseOutputText(text="Hello ", type="output_text", annotations=[])],
            role="assistant",
            status="in_progress",
            type="message",
        ),
        type="message_output_item",
        agent=agent,
    )
    msg_item2 = MessageOutputItem(
        raw_item=ResponseOutputMessage(
            id="msg_2",
            content=[ResponseOutputText(text="World", type="output_text", annotations=[])],
            role="assistant",
            status="completed",
            type="message",
        ),
        type="message_output_item",
        agent=agent,
    )

    async def dummy_stream():
        yield RunItemStreamEvent(name="message_output_created", item=msg_item1, type="run_item_stream_event")
        yield RunItemStreamEvent(name="message_output_created", item=msg_item2, type="run_item_stream_event")

    class DummyStreamedResult:
        def stream_events(self):
            return dummy_stream()

    with patch("agents.Runner.run_streamed", return_value=DummyStreamedResult()):
        events = []
        async for event in agent.get_response_stream(message_content):
            events.append(event)

        assert len(events) == 2
        for event in events:
            assert isinstance(event, RunItemStreamEvent)
            assert hasattr(event, "agent")
            assert event.agent == "TestAgent"
            assert hasattr(event, "callerAgent")
            assert event.callerAgent is None


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_stream_emits_preface_events_before_completion(mock_runner_run_streamed):
    """Ensure agent_updated/raw_response events still reach listeners when guardrails do not fire."""
    agent = Agent(name="TestAgent", instructions="Handle streaming")

    # Minimal objects emulating SDK preface events using real stream event types.
    updated_event = AgentUpdatedStreamEvent(new_agent=SDKAgent(name="PrefaceAgent", instructions="noop"))
    updated_event.id = "agent_run_preface"
    raw_response_event = RawResponsesStreamEvent(data={"status": "in_progress"})

    msg_item = MessageOutputItem(
        raw_item=ResponseOutputMessage(
            id="msg_final",
            content=[ResponseOutputText(text="Final", type="output_text", annotations=[])],
            role="assistant",
            status="completed",
            type="message",
        ),
        type="message_output_item",
        agent=agent,
    )

    async def dummy_stream():
        yield updated_event
        yield raw_response_event
        yield RunItemStreamEvent(name="message_output_created", item=msg_item, type="run_item_stream_event")

    class DummyStreamedResult:
        def __init__(self) -> None:
            self.final_output = "Final"

        def stream_events(self):
            return dummy_stream()

        def to_input_list(self):
            return []

    mock_runner_run_streamed.return_value = DummyStreamedResult()

    stream = agent.get_response_stream("Process this")
    events = [event async for event in stream]

    assert [getattr(event, "type", None) for event in events] == [
        "agent_updated_stream_event",
        "raw_response_event",
        "run_item_stream_event",
    ]
    # Confirm the buffered events still carry through with attribution added.
    assert getattr(events[0], "agent_run_id", None) == "agent_run_preface"
    assert getattr(events[1], "type", None) == "raw_response_event"


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_get_response_stream_exposes_run_result(mock_runner_run_streamed):
    """Ensure streaming runs surface the final RunResultStreaming for downstream hooks."""
    agent = Agent(name="TestAgent", instructions="Test instructions")

    msg_item = MessageOutputItem(
        raw_item=ResponseOutputMessage(
            id="msg_final",
            content=[ResponseOutputText(text="Final result", type="output_text", annotations=[])],
            role="assistant",
            status="completed",
            type="message",
        ),
        type="message_output_item",
        agent=agent,
    )

    async def dummy_stream():
        yield RunItemStreamEvent(name="message_output_created", item=msg_item, type="run_item_stream_event")

    final_output_text = "stream final output"

    class DummyStreamedResult:
        def __init__(self) -> None:
            self.final_output = final_output_text

        def stream_events(self):
            return dummy_stream()

        def to_input_list(self):
            return []

    mock_runner_run_streamed.return_value = DummyStreamedResult()

    stream = agent.get_response_stream("Process this")

    events = []
    async for event in stream:
        events.append(event)

    assert events, "Streaming run should emit events"
    result = await stream.wait_final_result()
    assert result is not None
    assert result.final_output == final_output_text
    assert stream.final_output == final_output_text


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_agency_stream_propagates_final_output(mock_runner_run_streamed):
    agent = Agent(name="TestAgent", instructions="Handle tasks")
    agency = Agency(agent)

    msg_item = MessageOutputItem(
        raw_item=ResponseOutputMessage(
            id="msg_final",
            content=[ResponseOutputText(text="Agency final", type="output_text", annotations=[])],
            role="assistant",
            status="completed",
            type="message",
        ),
        type="message_output_item",
        agent=agent,
    )

    async def dummy_stream():
        yield RunItemStreamEvent(name="message_output_created", item=msg_item, type="run_item_stream_event")

    final_output_text = "agency stream final"

    class DummyStreamedResult:
        def __init__(self) -> None:
            self.final_output = final_output_text

        def stream_events(self):
            return dummy_stream()

        def to_input_list(self):
            return [{"role": "assistant", "content": final_output_text, "type": "message"}]

    mock_runner_run_streamed.return_value = DummyStreamedResult()

    stream = agency.get_response_stream("Process this")
    events = []
    async for event in stream:
        events.append(event)

    assert events, "Streaming through agency should emit events"
    result = await stream.wait_final_result()
    assert result is not None
    assert result.final_output == final_output_text
    assert stream.final_output == final_output_text


def test_get_response_stream_initialization_without_event_loop():
    agent = Agent(name="TestAgent", instructions="Prepare response")
    stream = agent.get_response_stream("Hello")
    assert isinstance(stream, StreamingRunResponse)
    assert stream.final_result is None


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_get_response_stream_with_run_config_sets_trace_id(mock_runner_run_streamed):
    agent = Agent(name="TestAgent", instructions="Trace awareness")
    run_config = RunConfig()

    msg_item = MessageOutputItem(
        raw_item=ResponseOutputMessage(
            id="msg_trace",
            content=[ResponseOutputText(text="Trace", type="output_text", annotations=[])],
            role="assistant",
            status="completed",
            type="message",
        ),
        type="message_output_item",
        agent=agent,
    )

    async def dummy_stream():
        yield RunItemStreamEvent(name="message_output_created", item=msg_item, type="run_item_stream_event")

    class DummyStreamedResult:
        def stream_events(self):
            return dummy_stream()

        def to_input_list(self):
            return []

    mock_runner_run_streamed.return_value = DummyStreamedResult()

    stream = agent.get_response_stream("ensure trace", run_config_override=run_config)

    async for _ in stream:
        pass

    assert isinstance(run_config.trace_id, str)
    assert run_config.trace_id.startswith("trace_")

    call_kwargs = mock_runner_run_streamed.call_args.kwargs
    assert "run_config" in call_kwargs
    assert call_kwargs["run_config"] is run_config


@pytest.mark.asyncio
async def test_get_response_stream_final_result_processing():
    """Validate metadata presence for RunItemStreamEvent objects in streaming.

    Ensures downstream consumers can attribute final output to the right agent,
    per the documented metadata contract.
    """
    agent = Agent(name="TestAgent", instructions="Test instructions")

    msg_item = MessageOutputItem(
        raw_item=ResponseOutputMessage(
            id="msg_final",
            content=[ResponseOutputText(text="Final result", type="output_text", annotations=[])],
            role="assistant",
            status="completed",
            type="message",
        ),
        type="message_output_item",
        agent=agent,
    )

    async def dummy_stream():
        yield RunItemStreamEvent(name="message_output_created", item=msg_item, type="run_item_stream_event")

    class DummyStreamedResult:
        def stream_events(self):
            return dummy_stream()

    with patch("agents.Runner.run_streamed", return_value=DummyStreamedResult()):
        events = []
        async for event in agent.get_response_stream("Process this"):
            events.append(event)

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, RunItemStreamEvent)
        assert hasattr(event, "agent")
        assert event.agent == "TestAgent"
        assert hasattr(event, "callerAgent")
        assert event.callerAgent is None


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
    """Ensure each new agent stream receives its own agent_run_id end-to-end."""

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
            self.type = "message_output_item"

        def to_input_item(self):
            # Minimal assistant message dict compatible with storage
            return {"role": "assistant", "content": self.text, "id": f"msg_{self.text}"}

    def make_run_item_event(item: DummyItem):
        return RunItemStreamEvent(name="message_output_created", item=item, type="run_item_stream_event")

    async def mock_stream_wrapper():
        # First agent instance
        yield make_new_agent_event("RiskAnalyst", "agent_updated_stream_event_AAAA")
        yield make_run_item_event(DummyItem("A"))
        # Second agent instance of the same name
        yield make_new_agent_event("RiskAnalyst", "agent_updated_stream_event_BBBB")
        yield make_run_item_event(DummyItem("B"))

    class MockStreamedResult:
        def stream_events(self):
            return mock_stream_wrapper()

    mock_runner_run_streamed_patch.return_value = MockStreamedResult()

    events = []
    async for event in minimal_agent.get_response_stream("Test message"):
        events.append(event)

    # Validate agent_run_id propagation on emitted events
    assert len(events) == 4
    assert getattr(events[0], "type", None) == "agent_updated_stream_event"
    assert getattr(events[0], "agent_run_id", None) == "agent_updated_stream_event_AAAA"
    assert getattr(events[1], "type", None) == "run_item_stream_event"
    assert events[1].agent_run_id == "agent_updated_stream_event_AAAA"

    assert getattr(events[2], "type", None) == "agent_updated_stream_event"
    assert getattr(events[2], "agent_run_id", None) == "agent_updated_stream_event_BBBB"
    assert getattr(events[3], "type", None) == "run_item_stream_event"
    assert events[3].agent_run_id == "agent_updated_stream_event_BBBB"

    # Validate saved assistant messages include the correct agent_run_id
    saved_batches = [call.args[0] for call in mock_thread_manager.add_messages.call_args_list]
    saved_msgs = [m for batch in saved_batches for m in batch]
    # Keep only assistant outputs created from stream items in this test
    saved_assistant = {m.get("id"): m for m in saved_msgs if isinstance(m, dict) and m.get("id", "").startswith("msg_")}
    assert set(saved_assistant.keys()) == {"msg_A", "msg_B"}
    assert saved_assistant["msg_A"]["agent_run_id"] == "agent_updated_stream_event_AAAA"
    assert saved_assistant["msg_B"]["agent_run_id"] == "agent_updated_stream_event_BBBB"


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_streaming_persists_hosted_tool_outputs(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    """Ensure streaming persists hosted tool outputs via extract_hosted_tool_results."""

    msg_item = MessageOutputItem(
        raw_item=ResponseOutputMessage(
            id="msg_stream_hosted",
            content=[ResponseOutputText(text="Final answer", type="output_text", annotations=[])],
            role="assistant",
            status="completed",
            type="message",
        ),
        type="message_output_item",
        agent=minimal_agent,
    )

    class DummyStreamedResult:
        def __init__(self, input_history):
            self._input_history = input_history
            self.new_items = [msg_item]  # Required for new persistence implementation

        def stream_events(self):
            async def _gen():
                yield RunItemStreamEvent(
                    name="message_output_created",
                    item=msg_item,
                    type="run_item_stream_event",
                )

            return _gen()

        def to_input_list(self):
            return self._input_history + [msg_item.to_input_item()]

        def cancel(self):
            return None

    def _run_streamed_stub(*args, **kwargs):
        return DummyStreamedResult(kwargs.get("input", []))

    mock_runner_run_streamed_patch.side_effect = _run_streamed_stub

    hosted_message = MessageFormatter.add_agency_metadata(
        {
            "role": "system",
            "content": "[SEARCH_RESULTS] Tool Call ID: call-123",
            "message_origin": "file_search_preservation",
        },
        agent="TestAgent",
        caller_agent=None,
    )

    mock_thread_manager.replace_messages.reset_mock()

    with patch(
        "agency_swarm.agent.execution_stream_persistence.MessageFormatter.extract_hosted_tool_results",
        return_value=[hosted_message],
    ) as mock_extract:
        async for _ in minimal_agent.get_response_stream("search the files"):
            pass

    assert mock_extract.called, "Hosted tool outputs should be extracted during streaming persistence"

    assert mock_thread_manager.replace_messages.called, "Streaming persistence should rebuild message history"
    persisted_history = mock_thread_manager.replace_messages.call_args_list[-1][0][0]
    assert any(item.get("message_origin") == "file_search_preservation" for item in persisted_history), (
        "Hosted tool outputs should be included in persisted history"
    )


def test_streaming_forwarded_items_preserve_caller_metadata(monkeypatch, mock_thread_manager):
    """Forwarded run items must retain their original caller metadata when persisted."""
    worker = Agent(name="Worker", instructions="Delegates work")
    analyst = Agent(name="Analyst", instructions="Research specialist")

    forwarded_raw = ResponseOutputMessage(
        id="forwarded_msg",
        content=[ResponseOutputText(text="Analysis", type="output_text", annotations=[])],
        role="assistant",
        status="completed",
        type="message",
    )
    forwarded_item = MessageOutputItem(agent=analyst, raw_item=forwarded_raw)
    forwarded_payload = dict(forwarded_item.to_input_item())
    forwarded_payload["callerAgent"] = worker.name

    agency_context = AgencyContext(agency_instance=MagicMock(), thread_manager=mock_thread_manager)

    # Track metadata for the forwarded item - this simulates what happens during streaming
    # when the item's caller is captured (4-tuple: agent_name, agent_run_id, caller_name, timestamp)
    metadata_store = StreamMetadataStore(
        by_item={id(forwarded_item): (analyst.name, "agent_run_analyst", worker.name, 1000000)}
    )

    class DummyStreamResult:
        def __init__(self):
            self.new_items = [forwarded_item]  # Provide actual RunItem objects

        def to_input_list(self) -> list[dict[str, object]]:
            return [forwarded_payload]

    stream_result = DummyStreamResult()

    monkeypatch.setattr(
        "agency_swarm.agent.execution_stream_persistence.MessageFormatter.extract_hosted_tool_results",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "agency_swarm.agent.execution_stream_persistence.MessageFilter.should_filter",
        lambda _item: False,
    )
    monkeypatch.setattr(
        "agency_swarm.agent.execution_stream_persistence.MessageFilter.filter_messages",
        lambda items: items,
    )

    _persist_streamed_items(
        streaming_result=stream_result,
        metadata_store=metadata_store,
        collected_items=[forwarded_item],
        agent=worker,
        sender_name="Manager",
        parent_run_id=None,
        run_trace_id="trace_forwarded",
        fallback_agent_run_id="agent_run_worker",
        agency_context=agency_context,
        initial_saved_count=0,
    )

    mock_thread_manager.replace_messages.assert_called()
    persisted = mock_thread_manager.replace_messages.call_args[0][0]
    assert persisted, "Forwarded item must be persisted to thread history"
    saved_entry = persisted[-1]
    assert saved_entry.get("callerAgent") == worker.name, (
        "Forwarded item should retain the original caller, not the top-level sender"
    )


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_streaming_persists_items_with_timestamps(
    mock_runner_run_streamed_patch,
    minimal_agent,
    mock_thread_manager,
):
    """End-to-end test verifying that streaming persists items with timestamps.

    This tests that items persisted through the streaming flow have timestamps attached.
    """
    msg_item_1 = MessageOutputItem(
        raw_item=ResponseOutputMessage(
            id="msg_e2e_1",
            content=[ResponseOutputText(text="First", type="output_text", annotations=[])],
            role="assistant",
            status="completed",
            type="message",
        ),
        type="message_output_item",
        agent=minimal_agent,
    )
    msg_item_2 = MessageOutputItem(
        raw_item=ResponseOutputMessage(
            id="msg_e2e_2",
            content=[ResponseOutputText(text="Second", type="output_text", annotations=[])],
            role="assistant",
            status="completed",
            type="message",
        ),
        type="message_output_item",
        agent=minimal_agent,
    )

    async def mock_stream():
        yield RunItemStreamEvent(name="message_output_created", item=msg_item_1, type="run_item_stream_event")
        yield RunItemStreamEvent(name="message_output_created", item=msg_item_2, type="run_item_stream_event")

    class DummyStreamedResult:
        def __init__(self):
            self.new_items = [msg_item_1, msg_item_2]

        def stream_events(self):
            return mock_stream()

        def to_input_list(self):
            return [msg_item_1.to_input_item(), msg_item_2.to_input_item()]

        def cancel(self, mode=None):
            pass

    mock_runner_run_streamed_patch.return_value = DummyStreamedResult()

    events = []
    async for event in minimal_agent.get_response_stream("test"):
        events.append(event)

    # Verify at least 2 events were streamed
    assert len(events) >= 2, "Should have streamed at least 2 events"

    # Verify replace_messages was called (final persistence)
    assert mock_thread_manager.replace_messages.called, "Should persist messages"
    persisted = mock_thread_manager.replace_messages.call_args[0][0]

    # Find the persisted items
    saved_by_id = {item.get("id"): item for item in persisted if isinstance(item, dict)}

    # Both items should have timestamps
    if "msg_e2e_1" in saved_by_id:
        ts1 = saved_by_id["msg_e2e_1"].get("timestamp")
        assert ts1 is not None, "First message should have a timestamp"

    if "msg_e2e_2" in saved_by_id:
        ts2 = saved_by_id["msg_e2e_2"].get("timestamp")
        assert ts2 is not None, "Second message should have a timestamp"

    # Timestamps should be in non-decreasing order (may be equal if processed quickly)
    if "msg_e2e_1" in saved_by_id and "msg_e2e_2" in saved_by_id:
        ts1 = saved_by_id["msg_e2e_1"].get("timestamp", 0)
        ts2 = saved_by_id["msg_e2e_2"].get("timestamp", 0)
        assert ts1 <= ts2, f"Timestamps should be in non-decreasing order: first ({ts1}) <= second ({ts2})"


def test_persist_streamed_items_uses_python_object_id_matching(monkeypatch, mock_thread_manager):
    """Verify metadata is correctly matched using Python object id().

    This tests that the new matching approach using Python object identity works
    correctly regardless of message ID values (works for both OpenAI and LiteLLM).
    """
    agent = Agent(name="TestAgent", instructions="Test object id matching")

    # Create two message items
    msg_item_1 = MessageOutputItem(
        raw_item=ResponseOutputMessage(
            id="msg_1",
            content=[ResponseOutputText(text="First message", type="output_text", annotations=[])],
            role="assistant",
            status="completed",
            type="message",
        ),
        type="message_output_item",
        agent=agent,
    )
    msg_item_2 = MessageOutputItem(
        raw_item=ResponseOutputMessage(
            id="msg_2",
            content=[ResponseOutputText(text="Second message", type="output_text", annotations=[])],
            role="assistant",
            status="completed",
            type="message",
        ),
        type="message_output_item",
        agent=agent,
    )

    # Track metadata by Python object id() - simulating what happens during streaming
    # 4-tuple: (agent_name, agent_run_id, caller_name, timestamp)
    metadata_store = StreamMetadataStore(
        by_item={
            id(msg_item_1): ("Agent1", "run_1", "Caller1", 1000000),
            id(msg_item_2): ("Agent2", "run_2", "Caller2", 2000000),
        }
    )

    class DummyStreamResult:
        def __init__(self):
            self.new_items = [msg_item_1, msg_item_2]

        def to_input_list(self) -> list[dict[str, object]]:
            return [msg_item_1.to_input_item(), msg_item_2.to_input_item()]

    stream_result = DummyStreamResult()
    agency_context = AgencyContext(agency_instance=MagicMock(), thread_manager=mock_thread_manager)

    monkeypatch.setattr(
        "agency_swarm.agent.execution_stream_persistence.MessageFormatter.extract_hosted_tool_results",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "agency_swarm.agent.execution_stream_persistence.MessageFilter.should_filter",
        lambda _item: False,
    )
    monkeypatch.setattr(
        "agency_swarm.agent.execution_stream_persistence.MessageFilter.filter_messages",
        lambda items: items,
    )

    _persist_streamed_items(
        streaming_result=stream_result,
        metadata_store=metadata_store,
        collected_items=[msg_item_1, msg_item_2],
        agent=agent,
        sender_name=None,
        parent_run_id=None,
        run_trace_id="trace_obj_id",
        fallback_agent_run_id="run_fallback",
        agency_context=agency_context,
        initial_saved_count=0,
    )

    mock_thread_manager.replace_messages.assert_called()
    persisted = mock_thread_manager.replace_messages.call_args[0][0]
    assert len(persisted) >= 2, "Both items should be persisted"

    # Find the persisted items by their message id
    saved_by_id = {item.get("id"): item for item in persisted if isinstance(item, dict)}

    # Verify metadata was correctly matched using Python object id()
    assert saved_by_id["msg_1"]["agent"] == "Agent1", "First message should have Agent1"
    assert saved_by_id["msg_1"]["agent_run_id"] == "run_1", "First message should have run_1"
    assert saved_by_id["msg_1"]["callerAgent"] == "Caller1", "First message should have Caller1"

    assert saved_by_id["msg_2"]["agent"] == "Agent2", "Second message should have Agent2"
    assert saved_by_id["msg_2"]["agent_run_id"] == "run_2", "Second message should have run_2"
    assert saved_by_id["msg_2"]["callerAgent"] == "Caller2", "Second message should have Caller2"

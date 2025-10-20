from unittest.mock import MagicMock, patch

import pytest
from agents import RunConfig
from agents.lifecycle import RunHooks
from agents.stream_events import RunItemStreamEvent

from agency_swarm import Agency, Agent, StreamingRunResponse

from ._streaming_helpers import build_message_item, make_stream_result


@pytest.mark.asyncio
async def test_get_response_stream_basic():
    agent = Agent(name="TestAgent", instructions="Test instructions")
    message_content = "Stream this"

    msg_item1 = build_message_item("msg_1", "Hello ")
    msg_item2 = build_message_item("msg_2", "World")

    stream_result = make_stream_result(
        [
            RunItemStreamEvent(name="message_output_created", item=msg_item1, type="run_item_stream_event"),
            RunItemStreamEvent(name="message_output_created", item=msg_item2, type="run_item_stream_event"),
        ],
    )

    with patch("agents.Runner.run_streamed", return_value=stream_result):
        events = []
        async for event in agent.get_response_stream(message_content):
            events.append(event)

        assert len(events) == 2
        for event in events:
            assert isinstance(event, RunItemStreamEvent)
            assert getattr(event, "agent", None) == "TestAgent"
            assert getattr(event, "callerAgent", None) is None


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_get_response_stream_exposes_run_result(mock_runner_run_streamed):
    agent = Agent(name="TestAgent", instructions="Test instructions")
    msg_item = build_message_item("msg_final", "Final result")

    mock_runner_run_streamed.return_value = make_stream_result(
        [RunItemStreamEvent(name="message_output_created", item=msg_item, type="run_item_stream_event")],
        final_output="stream final output",
    )

    stream = agent.get_response_stream("Process this")
    events = [event async for event in stream]

    assert events
    result = await stream.wait_final_result()
    assert result is not None
    assert result.final_output == "stream final output"
    assert stream.final_output == "stream final output"


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_agency_stream_propagates_final_output(mock_runner_run_streamed):
    agent = Agent(name="TestAgent", instructions="Handle tasks")
    agency = Agency(agent)
    msg_item = build_message_item("msg_final", "Agency final")

    mock_runner_run_streamed.return_value = make_stream_result(
        [RunItemStreamEvent(name="message_output_created", item=msg_item, type="run_item_stream_event")],
        history_snapshot=[{"role": "assistant", "content": "Agency final", "type": "message"}],
        final_output="agency stream final",
    )

    stream = agency.get_response_stream("Process this")
    events = [event async for event in stream]

    assert events
    result = await stream.wait_final_result()
    assert result is not None
    assert result.final_output == "agency stream final"
    assert stream.final_output == "agency stream final"


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
    msg_item = build_message_item("msg_trace", "Trace")

    mock_runner_run_streamed.return_value = make_stream_result(
        [RunItemStreamEvent(name="message_output_created", item=msg_item, type="run_item_stream_event")]
    )

    stream = agent.get_response_stream("ensure trace", run_config_override=run_config)
    async for _ in stream:
        pass

    assert isinstance(run_config.trace_id, str) and run_config.trace_id.startswith("trace_")
    call_kwargs = mock_runner_run_streamed.call_args.kwargs
    assert call_kwargs["run_config"] is run_config


@pytest.mark.asyncio
async def test_get_response_stream_final_result_processing():
    agent = Agent(name="TestAgent", instructions="Test instructions")
    msg_item = build_message_item("msg_final", "Final result")

    stream_result = make_stream_result(
        [RunItemStreamEvent(name="message_output_created", item=msg_item, type="run_item_stream_event")]
    )

    with patch("agents.Runner.run_streamed", return_value=stream_result):
        events = [event async for event in agent.get_response_stream("Process this")]

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, RunItemStreamEvent)
    assert getattr(event, "agent", None) == "TestAgent"
    assert getattr(event, "callerAgent", None) is None


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_get_response_stream_generates_thread_id(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    mock_runner_run_streamed_patch.return_value = make_stream_result(
        [{"event": "text", "data": "Hello"}, {"event": "done"}]
    )

    events = [event async for event in minimal_agent.get_response_stream("Test message")]
    assert len(events) == 2
    mock_thread_manager.add_messages.assert_called()
    messages = mock_thread_manager.add_messages.call_args[0][0]
    assert messages and all(msg.get("agent") == "TestAgent" for msg in messages)


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_get_response_stream_agent_to_agent_communication(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    from agency_swarm.agent.core import AgencyContext

    mock_runner_run_streamed_patch.return_value = make_stream_result(
        [{"event": "text", "data": "Hello"}, {"event": "done"}]
    )

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

    events = [
        event
        async for event in minimal_agent.get_response_stream(
            "Test message", sender_name="SomeAgent", agency_context=agency_context
        )
    ]
    assert len(events) == 2
    messages = mock_thread_manager.add_messages.call_args[0][0]
    assert all(msg.get("agent") == "TestAgent" for msg in messages)
    assert all(msg.get("callerAgent") == "SomeAgent" for msg in messages)


@pytest.mark.asyncio
async def test_get_response_stream_input_validation_none_empty(minimal_agent, mock_thread_manager):
    events = [event async for event in minimal_agent.get_response_stream(None)]
    assert len(events) == 1 and events[0]["type"] == "error"
    assert "cannot be None" in events[0]["content"]

    events = [event async for event in minimal_agent.get_response_stream("   ")]
    assert len(events) == 1 and events[0]["type"] == "error"
    assert "cannot be empty" in events[0]["content"]


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_get_response_stream_context_propagation(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    mock_runner_run_streamed_patch.return_value = make_stream_result(
        [{"event": "text", "data": "Hello"}, {"event": "done"}]
    )

    context_override = {"test_key": "test_value"}
    hooks_override = MagicMock(spec=RunHooks)

    events = [
        event
        async for event in minimal_agent.get_response_stream(
            "Test message", context_override=context_override, hooks_override=hooks_override
        )
    ]

    assert len(events) == 2
    mock_runner_run_streamed_patch.assert_called_once()
    call_kwargs = mock_runner_run_streamed_patch.call_args.kwargs
    assert call_kwargs["hooks"] is hooks_override


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_get_response_stream_thread_management(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    mock_runner_run_streamed_patch.return_value = make_stream_result(
        [{"event": "text", "data": "Hello"}, {"event": "done"}]
    )

    events = [event async for event in minimal_agent.get_response_stream("Test message")]
    assert len(events) == 2
    mock_thread_manager.add_messages.assert_called()
    messages = mock_thread_manager.add_messages.call_args[0][0]
    assert all(msg.get("agent") == "TestAgent" for msg in messages)
    assert all(msg.get("callerAgent") is None for msg in messages)


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_stream_assigns_stable_agent_run_id_per_new_agent(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    class Obj:
        pass

    def make_new_agent_event(agent_name: str, event_id: str):
        event = Obj()
        event.type = "agent_updated_stream_event"
        new_agent = Obj()
        new_agent.name = agent_name
        event.new_agent = new_agent
        event.id = event_id
        return event

    class DummyItem:
        def __init__(self, text: str):
            self.text = text
            self.type = "message_output_item"

        def to_input_item(self):
            return {"role": "assistant", "content": self.text, "id": f"msg_{self.text}"}

    def make_run_item_event(item: DummyItem):
        return RunItemStreamEvent(name="message_output_created", item=item, type="run_item_stream_event")

    mock_runner_run_streamed_patch.return_value = make_stream_result(
        [
            make_new_agent_event("RiskAnalyst", "agent_updated_stream_event_AAAA"),
            make_run_item_event(DummyItem("A")),
            make_new_agent_event("RiskAnalyst", "agent_updated_stream_event_BBBB"),
            make_run_item_event(DummyItem("B")),
        ]
    )

    events = [event async for event in minimal_agent.get_response_stream("Test message")]

    assert getattr(events[0], "agent_run_id", None) == "agent_updated_stream_event_AAAA"
    assert getattr(events[1], "agent_run_id", None) == "agent_updated_stream_event_AAAA"
    assert getattr(events[2], "agent_run_id", None) == "agent_updated_stream_event_BBBB"
    assert getattr(events[3], "agent_run_id", None) == "agent_updated_stream_event_BBBB"

    saved_batches = [call.args[0] for call in mock_thread_manager.add_messages.call_args_list]
    saved_msgs = [msg for batch in saved_batches for msg in batch]
    saved_assistant = {
        msg.get("id"): msg for msg in saved_msgs if isinstance(msg, dict) and msg.get("id", "").startswith("msg_")
    }

    assert saved_assistant["msg_A"]["agent_run_id"] == "agent_updated_stream_event_AAAA"
    assert saved_assistant["msg_B"]["agent_run_id"] == "agent_updated_stream_event_BBBB"

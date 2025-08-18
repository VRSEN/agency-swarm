from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agency_swarm import Agent
from agency_swarm.agent_core import AgencyContext
from agency_swarm.tools.send_message import SendMessage


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_initiating_message_has_agent_run_id_non_stream(mock_runner_run, minimal_agent, mock_thread_manager):
    mock_runner_run.return_value = MagicMock(new_items=[], final_output="ok")

    await minimal_agent.get_response("Hello there")

    saved_batches = [call.args[0] for call in mock_thread_manager.add_messages.call_args_list]
    saved_msgs = [m for batch in saved_batches for m in batch]

    user_msgs = [m for m in saved_msgs if m.get("role") == "user"]
    assert user_msgs
    assert all("agent_run_id" in m and isinstance(m["agent_run_id"], str) and m["agent_run_id"] for m in user_msgs)


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_initiating_message_has_agent_run_id_agent_to_agent(mock_runner_run, mock_thread_manager):
    mock_runner_run.return_value = MagicMock(new_items=[], final_output="ok")

    recipient = Agent(name="Recipient", instructions="i")

    mock_agency = MagicMock()
    mock_agency.agents = {"Recipient": recipient}
    mock_agency.user_context = {}

    agency_context = AgencyContext(
        agency_instance=mock_agency,
        thread_manager=mock_thread_manager,
        subagents={},
        load_threads_callback=None,
        save_threads_callback=None,
        shared_instructions=None,
    )

    await recipient.get_response(message="From Sender", sender_name="Sender", agency_context=agency_context)

    saved_batches = [call.args[0] for call in mock_thread_manager.add_messages.call_args_list]
    saved_msgs = [m for batch in saved_batches for m in batch]

    user_msgs = [m for m in saved_msgs if m.get("role") == "user" and m.get("agent") == "Recipient"]
    assert user_msgs
    assert all("agent_run_id" in m and isinstance(m["agent_run_id"], str) and m["agent_run_id"] for m in user_msgs)


class _DummyStreamingContext:
    def __init__(self):
        self._events = []

    async def put_event(self, event):
        self._events.append(event)


@pytest.mark.asyncio
async def test_send_message_sentinel_persists_and_event_has_agent_run_id(mock_thread_manager):
    sender = Agent(name="PortfolioManager", instructions="i")
    recipient = Agent(name="RiskAnalyst", instructions="i")
    tool = SendMessage(sender_agent=sender, recipients={recipient.name.lower(): recipient})

    class _Ctx:
        def __init__(self):
            self._is_streaming = True
            self._streaming_context = _DummyStreamingContext()
            self._current_agent_run_id = "agent_run_TESTCASE"
            self.thread_manager = mock_thread_manager
            self.agents = {sender.name: sender, recipient.name: recipient}
            self.user_context = {}
            self.shared_instructions = None

    class _Wrapper:
        def __init__(self):
            self.context = _Ctx()

    wrapper = _Wrapper()

    async def _empty_stream(*args, **kwargs):
        if False:
            yield  # pragma: no cover
        return

    recipient.get_response_stream = _empty_stream  # type: ignore[attr-defined]

    import json

    # Keep content minimal to satisfy linter while preserving test semantics
    arguments_json = {
        "recipient_agent": "RiskAnalyst",
        "my_primary_instructions": "Conduct risk assessment.",
        "message": "Analyze AAPL risk profile.",
        "additional_instructions": "Tech sector context.",
    }
    arguments_json_string = json.dumps(arguments_json)

    await tool.on_invoke_tool(wrapper, arguments_json_string)

    # Event tagged
    sc = wrapper.context._streaming_context
    assert sc._events
    ev = sc._events[0]
    assert getattr(ev, "agent_run_id", None) == "agent_run_TESTCASE"

    # Persisted sentinel tagged
    mock_thread_manager.add_messages.assert_called()
    saved_batches = [call.args[0] for call in mock_thread_manager.add_messages.call_args_list]
    flat = [m for batch in saved_batches for m in batch]
    fc = next(
        (
            m
            for m in flat
            if isinstance(m, dict) and m.get("type") == "function_call" and m.get("name") == "send_message"
        ),
        None,
    )
    assert fc is not None
    assert fc.get("agent_run_id") == "agent_run_TESTCASE"


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_runner_input_strips_agent_run_id_non_stream(mock_runner_run, minimal_agent, mock_thread_manager):
    class DummyRunResult:
        new_items = []
        final_output = "done"

    captured_input = {}

    async def _fake_run(**kwargs):
        captured_input["input"] = kwargs.get("input", [])
        return DummyRunResult()

    mock_runner_run.side_effect = _fake_run

    mock_thread_manager.add_messages(
        [
            {
                "role": "user",
                "content": "hello",
                "agent": "TestAgent",
                "callerAgent": None,
                "timestamp": 1,
                "agent_run_id": "agent_run_PRE",
            }
        ]
    )

    await minimal_agent.get_response("Next")

    assert "input" in captured_input
    assert all("agent_run_id" not in m for m in captured_input["input"])


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_runner_input_strips_agent_run_id_stream(mock_run_streamed, minimal_agent, mock_thread_manager):
    mock_thread_manager.add_messages(
        [
            {
                "type": "function_call",
                "agent": "TestAgent",
                "callerAgent": None,
                "name": "send_message",
                "arguments": "{}",
                "call_id": "call_ABC",
                "id": "fc_ABC",
                "status": "in_progress",
                "timestamp": 1,
                "agent_run_id": "agent_run_PRE_STREAM",
            }
        ]
    )

    async def dummy_stream():
        if False:
            yield  # pragma: no cover
        return

    class DummyStreamedResult:
        def stream_events(self):
            return dummy_stream()

    captured = {}

    def _run_streamed_side_effect(**kwargs):
        captured["input"] = kwargs.get("input", [])
        return DummyStreamedResult()

    mock_run_streamed.side_effect = _run_streamed_side_effect

    async for _ in minimal_agent.get_response_stream("Hello streaming"):
        pass

    assert "input" in captured
    assert all("agent_run_id" not in m for m in captured["input"])

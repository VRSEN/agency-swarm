from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agency_swarm import Agent
from agency_swarm.agent_core import AgencyContext
from agency_swarm.tools.send_message import SendMessage


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_non_streaming_initiating_message_has_agent_run_id(mock_runner_run, minimal_agent, mock_thread_manager):
    """The first saved 'user' message for a run should include agent_run_id."""

    mock_runner_run.return_value = MagicMock(new_items=[], final_output="ok")

    await minimal_agent.get_response("Hello there")

    # Gather all saved messages from mocked thread manager calls
    saved_batches = [call.args[0] for call in mock_thread_manager.add_messages.call_args_list]
    saved_msgs = [m for batch in saved_batches for m in batch]

    assert any(m.get("role") == "user" for m in saved_msgs)

    user_msgs = [m for m in saved_msgs if m.get("role") == "user"]
    assert all("agent_run_id" in m and isinstance(m["agent_run_id"], str) and m["agent_run_id"] for m in user_msgs)


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_agent_to_agent_initiating_message_has_agent_run_id(mock_runner_run, mock_thread_manager):
    """Agent-to-agent initiating message saved for the recipient contains agent_run_id."""

    mock_runner_run.return_value = MagicMock(new_items=[], final_output="ok")

    recipient = Agent(name="Recipient", instructions="i")

    # Build a minimal AgencyContext mapping so recipient can run with thread manager
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

    # The first saved message for this run is the initiating 'user' message
    user_msgs = [m for m in saved_msgs if m.get("role") == "user" and m.get("agent") == "Recipient"]
    assert user_msgs, "Expected at least one initiating user message saved for recipient"
    assert all("agent_run_id" in m and isinstance(m["agent_run_id"], str) and m["agent_run_id"] for m in user_msgs)


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_runner_input_strips_agent_run_id(mock_runner_run, minimal_agent, mock_thread_manager):
    """Ensure input to Runner has no agent_run_id even if history contains it."""

    class DummyRunResult:
        new_items = []
        final_output = "done"

    captured_input = {}

    async def _fake_run(**kwargs):
        captured_input["input"] = kwargs.get("input", [])
        return DummyRunResult()

    mock_runner_run.side_effect = _fake_run

    # Preload mock store with messages that have agent_run_id
    preloaded = [
        {
            "role": "user",
            "content": "hello",
            "agent": "TestAgent",
            "callerAgent": None,
            "timestamp": 1,
            "agent_run_id": "agent_run_PRE",
        },
    ]
    # Use the side-effect to add to the internal list
    mock_thread_manager.add_messages(preloaded)

    await minimal_agent.get_response("Next")

    assert "input" in captured_input
    assert all("agent_run_id" not in m for m in captured_input["input"])


class _DummyStreamingContext:
    def __init__(self):
        self._events = []

    async def put_event(self, event):
        self._events.append(event)


@pytest.mark.asyncio
async def test_send_message_function_call_persists_agent_run_id(mock_thread_manager):
    """Streaming sentinel for send_message should persist agent_run_id on minimal record."""

    sender = Agent(name="PortfolioManager", instructions="i")
    recipient = Agent(name="RiskAnalyst", instructions="i")
    tool = SendMessage(sender_agent=sender, recipients={recipient.name.lower(): recipient})

    # Minimal wrapper-like object with context attributes accessed by tool
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

    # Stub recipient stream to end immediately
    async def _empty_stream(*args, **kwargs):
        if False:
            yield  # pragma: no cover
        return

    recipient.get_response_stream = _empty_stream  # type: ignore[attr-defined]

    # Invoke tool in streaming mode
    arguments_json_string = '{"recipient_agent":"RiskAnalyst","my_primary_instructions":"Conduct risk assessment on the given market data for Apple (AAPL). Provide insights into volatility, valuation risks, and sector-specific concerns.","message":"Please analyze the risk profile for Apple Inc. (AAPL) using the following market data: Current Price: $231.59, Market Cap: $3.437T, P/E Ratio: 35.089394, Forward P/E: 27.868832, Analyst Rating: buy. Focus on volatility, valuation risks, and sector-specific concerns.","additional_instructions":"The company operates in the Technology sector, specifically in the Consumer Electronics industry."}'

    await tool.on_invoke_tool(wrapper, arguments_json_string)

    # Validate streamed event includes agent_run_id
    sc = wrapper.context._streaming_context
    assert sc._events, "Expected a tool_called event emitted"
    ev = sc._events[0]
    assert getattr(ev, "agent_run_id", None) == "agent_run_TESTCASE"

    # Inspect saved minimal function_call record for agent_run_id
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
    assert fc is not None, "Expected send_message function_call record saved"
    # This is the specific requirement
    assert fc.get("agent_run_id") == "agent_run_TESTCASE"

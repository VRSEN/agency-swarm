from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agency_swarm import Agent, GuardrailFunctionOutput, OutputGuardrailTripwireTriggered, ThreadManager
from agency_swarm.agent.core import AgencyContext


def _make_tripwire(agent_output: str, guidance: str) -> OutputGuardrailTripwireTriggered:
    class _GuardrailObj:
        pass

    guardrail_result = type(
        "_OutputGuardrailResult",
        (),
        {
            "agent_output": agent_output,
            "output": GuardrailFunctionOutput(output_info=guidance, tripwire_triggered=True),
            "guardrail": _GuardrailObj(),
        },
    )()

    return OutputGuardrailTripwireTriggered(guardrail_result)


@pytest.mark.asyncio
@patch("agency_swarm.agent.execution_helpers.Runner.run", new_callable=AsyncMock)
async def test_output_guardrail_retries_update_history(mock_runner_run):
    agent = Agent(name="RetryAgent", instructions="Test", validation_attempts=1)

    # Prepare minimal agency context to capture messages
    ctx = AgencyContext(agency_instance=None, thread_manager=ThreadManager(), subagents={})

    # First attempt trips, second returns a minimal RunResult-like object
    mock_runner_run.side_effect = [
        _make_tripwire(agent_output="BAD OUTPUT", guidance="ERROR: fix format"),
        MagicMock(new_items=[], final_output="GOOD"),
    ]

    # Execute
    res = await agent.get_response(message="What is openai?", agency_context=ctx)
    assert getattr(res, "final_output", None) == "GOOD"

    # Validate conversation history contains initial user, appended assistant, appended user guidance
    all_msgs = ctx.thread_manager.get_all_messages()
    # Extract role and content for clarity
    trio = [(m.get("role"), m.get("content")) for m in all_msgs]
    # Expect at least 3 messages; find the last three
    assert ("user", "What is openai?") in trio
    assert ("assistant", "BAD OUTPUT") in trio
    assert ("system", "ERROR: fix format") in trio

    # The guidance system message should be classified as an output guardrail error
    sys_msgs = [m for m in all_msgs if m.get("role") == "system"]
    assert sys_msgs and sys_msgs[-1].get("message_origin") == "output_guardrail_error"


class _DummyStream:
    def __init__(self, events):
        self._events = events

    async def stream_events(self):
        for ev in self._events:
            yield ev

    def cancel(self):
        pass


class _SimpleEvent:
    def __init__(self, t: str):
        self.type = t


@pytest.mark.asyncio
@patch("agency_swarm.agent.execution_helpers.Runner.run_streamed")
async def test_output_guardrail_retries_streaming(mock_run_streamed):
    agent = Agent(name="RetryStreamAgent", instructions="Test", validation_attempts=1)
    ctx = AgencyContext(agency_instance=None, thread_manager=ThreadManager(), subagents={})

    # First call raises; second returns a dummy stream with one event
    mock_run_streamed.side_effect = [
        _make_tripwire(agent_output="STREAM BAD", guidance="ERROR: needs header"),
        _DummyStream([_SimpleEvent("run_item_stream_event")]),
    ]

    # Collect streamed events
    received = []
    async for ev in agent.get_response_stream(message="Hello", agency_context=ctx):
        received.append(ev)

    assert received, "expected events from second attempt"

    # The guidance user message should be in history
    msgs = ctx.thread_manager.get_all_messages()
    roles_contents = [(m.get("role"), m.get("content")) for m in msgs]
    assert ("system", "ERROR: needs header") in roles_contents

import pytest

from agency_swarm import Agent, GuardrailFunctionOutput, OutputGuardrailTripwireTriggered, ThreadManager
from agency_swarm.agent.core import AgencyContext


class _DummyRunResult:
    def __init__(self, output: str = "OK"):
        self.new_items = []
        self.final_output = output


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
async def test_output_guardrail_retries_update_history(monkeypatch):
    agent = Agent(name="RetryAgent", instructions="Test", validation_attempts=1)

    # Prepare minimal agency context to capture messages
    ctx = AgencyContext(agency_instance=None, thread_manager=ThreadManager(), subagents={})

    calls = {"n": 0}

    async def fake_run(**kwargs):
        if calls["n"] == 0:
            calls["n"] += 1
            raise _make_tripwire(agent_output="BAD OUTPUT", guidance="ERROR: fix format")
        return _DummyRunResult("GOOD")

    monkeypatch.setattr("agency_swarm.agent.execution_helpers.Runner.run", staticmethod(fake_run))

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
    assert ("user", "ERROR: fix format") in trio


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
async def test_output_guardrail_retries_streaming(monkeypatch):
    agent = Agent(name="RetryStreamAgent", instructions="Test", validation_attempts=1)
    ctx = AgencyContext(agency_instance=None, thread_manager=ThreadManager(), subagents={})

    calls = {"n": 0}

    def fake_run_streamed(**kwargs):
        if calls["n"] == 0:
            calls["n"] += 1
            raise _make_tripwire(agent_output="STREAM BAD", guidance="ERROR: needs header")
        # Second attempt returns one simple event
        return _DummyStream([_SimpleEvent("run_item_stream_event")])

    monkeypatch.setattr("agency_swarm.agent.execution_helpers.Runner.run_streamed", staticmethod(fake_run_streamed))

    # Collect streamed events
    received = []
    async for ev in agent.get_response_stream(message="Hello", agency_context=ctx):
        received.append(ev)

    assert received, "expected events from second attempt"

    # The guidance user message should be in history
    msgs = ctx.thread_manager.get_all_messages()
    roles_contents = [(m.get("role"), m.get("content")) for m in msgs]
    assert ("user", "ERROR: needs header") in roles_contents

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agency_swarm import (
    GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    ThreadManager,
)
from agency_swarm.agent.core import AgencyContext
from agency_swarm.agent.execution_streaming import prune_guardrail_messages


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_output_guardrail_auto_retry(mock_runner_run, minimal_agent, mock_thread_manager):
    class _Out:
        output_info = "fix it"

    class _OutputGuardrailResult:
        output = _Out()
        guardrail = object()

    mock_runner_run.side_effect = [
        OutputGuardrailTripwireTriggered(_OutputGuardrailResult()),
        MagicMock(new_items=[], final_output="ok"),
    ]

    result = await minimal_agent.get_response("Task: Demo")

    assert result.final_output == "ok"
    assert mock_runner_run.call_count == 2
    second_input = mock_runner_run.call_args_list[1].kwargs["input"]
    assert second_input[-1]["content"] == "fix it"


@pytest.mark.asyncio
async def test_input_guardrail_no_retry_streaming(monkeypatch, minimal_agent):
    agent = minimal_agent
    # Ensure multiple attempts available to prove no retry happens
    agent.validation_attempts = 2
    agent.raise_input_guardrail_error = True

    ctx = AgencyContext(agency_instance=None, thread_manager=ThreadManager(), subagents={})

    calls = {"n": 0}

    def fake_run_streamed(**kwargs):
        calls["n"] += 1

        class _InRes:
            output = GuardrailFunctionOutput(
                output_info="Prefix your request with 'Task:'",
                tripwire_triggered=True,
            )
            guardrail = object()

        raise InputGuardrailTripwireTriggered(_InRes())

    monkeypatch.setattr(
        "agency_swarm.agent.execution_helpers.Runner.run_streamed",
        staticmethod(fake_run_streamed),
    )

    received: list[object] = []
    stream = agent.get_response_stream(message="Hello", agency_context=ctx)
    with pytest.raises(InputGuardrailTripwireTriggered):
        async for ev in stream:
            received.append(ev)

    # Should surface an error event and not retry
    assert any(isinstance(ev, dict) and ev.get("type") == "error" for ev in received)
    err = next(ev for ev in received if isinstance(ev, dict) and ev.get("type") == "error")
    assert "Task:" in err.get("content", "")
    assert calls["n"] == 1

    # Validate persisted guidance is marked as input_guardrail_error in streaming mode
    msgs = ctx.thread_manager.get_all_messages()
    sys_msgs = [m for m in msgs if m.get("role") == "system"]
    assert sys_msgs and sys_msgs[-1].get("message_origin") == "input_guardrail_error"


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_input_guardrail_returns_error_non_stream(mock_runner_run, minimal_agent, mock_thread_manager):
    agent = minimal_agent
    agent.raise_input_guardrail_error = False

    class _InRes:
        output = GuardrailFunctionOutput(
            output_info="Prefix your request with 'Task:'",
            tripwire_triggered=True,
        )
        guardrail = object()

    mock_runner_run.side_effect = InputGuardrailTripwireTriggered(_InRes())

    ctx = AgencyContext(agency_instance=None, thread_manager=mock_thread_manager, subagents={})

    res = await agent.get_response(message="Hello", agency_context=ctx)

    assert res.final_output == "Prefix your request with 'Task:'"
    msgs = ctx.thread_manager.get_all_messages()
    roles_contents = [(m.get("role"), m.get("content")) for m in msgs]
    assert ("assistant", "Prefix your request with 'Task:'") in roles_contents
    assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]
    system_msgs = [m for m in msgs if m.get("role") == "system"]
    assert assistant_msgs and assistant_msgs[-1].get("message_origin") == "input_guardrail_message"
    assert not system_msgs


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_input_guardrail_error_no_assistant_messages(mock_runner_run, minimal_agent, mock_thread_manager):
    """When raise_input_guardrail_error=True, no assistant messages should persist."""
    agent = minimal_agent
    agent.raise_input_guardrail_error = True

    class _InRes:
        output = GuardrailFunctionOutput(
            output_info="Prefix your request with 'Task:'",
            tripwire_triggered=True,
        )
        guardrail = object()

    mock_runner_run.side_effect = InputGuardrailTripwireTriggered(_InRes())

    ctx = AgencyContext(agency_instance=None, thread_manager=mock_thread_manager, subagents={})

    with pytest.raises(InputGuardrailTripwireTriggered):
        await agent.get_response(message="Hello", agency_context=ctx)

    msgs = ctx.thread_manager.get_all_messages()

    # Should have exactly 2 messages: user input + system guardrail error
    assert len(msgs) == 2, f"Expected 2 messages (user + guardrail), got {len(msgs)}: {msgs}"

    # First message: user input
    assert msgs[0].get("role") == "user"
    assert msgs[0].get("content") == "Hello"

    # Second message: system guardrail error (not message)
    assert msgs[1].get("role") == "system"
    assert "Prefix your request with 'Task:'" in msgs[1].get("content", "")
    assert msgs[1].get("message_origin") == "input_guardrail_error"

    # Critical: NO assistant messages should be present
    assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]
    assert len(assistant_msgs) == 0, f"Expected no assistant messages, but found {len(assistant_msgs)}"


def test_prune_guardrail_messages_drops_subagent_history():
    """Input guardrail guidance must remove downstream agent chatter from history."""
    run_trace_id = "trace_123"
    messages = [
        {
            "role": "user",
            "content": "What is your support email address?",
            "agent": "CustomerSupportAgent",
            "callerAgent": None,
            "agent_run_id": "agent_run_parent",
            "run_trace_id": run_trace_id,
        },
        {
            "role": "user",
            "content": "Please provide the support email address.",
            "agent": "DatabaseAgent",
            "callerAgent": "CustomerSupportAgent",
            "agent_run_id": "agent_run_database",
            "run_trace_id": run_trace_id,
        },
        {
            "role": "user",
            "content": "Please provide the support email address.",
            "agent": "EmailAgent",
            "callerAgent": "DatabaseAgent",
            "agent_run_id": "agent_run_email",
            "run_trace_id": run_trace_id,
        },
        {
            "role": "system",
            "content": "Please, prefix your request with 'Support:'.",
            "message_origin": "input_guardrail_error",
            "agent": "EmailAgent",
            "callerAgent": "DatabaseAgent",
            "agent_run_id": "agent_run_email",
            "run_trace_id": run_trace_id,
        },
        {
            "role": "system",
            "content": "When chatting with this agent, provide your name (Alice).",
            "message_origin": "input_guardrail_error",
            "agent": "DatabaseAgent",
            "callerAgent": "CustomerSupportAgent",
            "agent_run_id": "agent_run_database",
            "run_trace_id": run_trace_id,
        },
        {
            "role": "assistant",
            "content": "Please, prefix your request with 'Support:' describing what you need.",
            "message_origin": "input_guardrail_message",
            "agent": "CustomerSupportAgent",
            "callerAgent": None,
            "agent_run_id": "agent_run_parent",
            "run_trace_id": run_trace_id,
        },
    ]

    cleaned = prune_guardrail_messages(
        messages,
        initial_saved_count=0,
        run_trace_id=run_trace_id,
        collapse_to_root=True,
    )

    assert cleaned == [messages[0], messages[-1]], cleaned
    assert all(msg.get("agent") == "CustomerSupportAgent" for msg in cleaned)
    assert [msg.get("role") for msg in cleaned] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_input_guardrail_streaming_strict_prunes_and_raises(monkeypatch, minimal_agent):
    agent = minimal_agent
    agent.raise_input_guardrail_error = True
    ctx = AgencyContext(agency_instance=None, thread_manager=ThreadManager(), subagents={})

    pruned_history = [{"role": "assistant", "content": "kept"}]
    observed_calls: list[dict[str, object]] = []

    def fake_prune(messages, *, initial_saved_count, run_trace_id, collapse_to_root):
        observed_calls.append(
            {
                "initial_saved_count": initial_saved_count,
                "run_trace_id": run_trace_id,
                "collapse_to_root": collapse_to_root,
                "message_count": len(messages),
            }
        )
        return list(pruned_history)

    monkeypatch.setattr("agency_swarm.agent.execution_streaming.prune_guardrail_messages", fake_prune)

    class _GuardrailResult:
        def __init__(self):
            self.output = GuardrailFunctionOutput(
                output_info="Please, prefix your request with 'Support:' describing what you need.",
                tripwire_triggered=True,
            )
            self.guardrail = object()

    class _FakeRunResult:
        def __init__(self):
            self.guardrail_result = _GuardrailResult()
            self.input_guardrail_results = [self.guardrail_result]
            self.new_items = []
            self.raw_responses = []
            self.final_output = ""

        async def stream_events(self):
            raise InputGuardrailTripwireTriggered(self.guardrail_result)
            yield  # pragma: no cover

        def cancel(self):
            return None

    monkeypatch.setattr("agents.Runner.run_streamed", staticmethod(lambda **_: _FakeRunResult()))

    stream = agent.get_response_stream(message="Hello", agency_context=ctx)

    with pytest.raises(InputGuardrailTripwireTriggered):
        async for _ in stream:
            pass

    assert observed_calls, "prune_guardrail_messages was not invoked"
    assert observed_calls[-1]["collapse_to_root"] is True
    assert ctx.thread_manager.get_all_messages() == pruned_history


@pytest.mark.asyncio
async def test_input_guardrail_streaming_friendly_prunes_and_streams(monkeypatch, minimal_agent):
    agent = minimal_agent
    agent.raise_input_guardrail_error = False
    ctx = AgencyContext(agency_instance=None, thread_manager=ThreadManager(), subagents={})

    pruned_history = [{"role": "assistant", "content": "friendly"}]
    prune_invocations = 0

    def fake_prune(messages, *, initial_saved_count, run_trace_id, collapse_to_root):
        nonlocal prune_invocations
        prune_invocations += 1
        return list(pruned_history)

    monkeypatch.setattr("agency_swarm.agent.execution_streaming.prune_guardrail_messages", fake_prune)

    class _GuardrailResult:
        def __init__(self):
            self.output = GuardrailFunctionOutput(
                output_info="Only support questions are allowed.",
                tripwire_triggered=True,
            )
            self.guardrail = object()

    class _FakeRunResult:
        def __init__(self):
            self.guardrail_result = _GuardrailResult()
            self.input_guardrail_results = [self.guardrail_result]
            self.new_items = []
            self.raw_responses = []
            self.final_output = ""

        async def stream_events(self):
            raise InputGuardrailTripwireTriggered(self.guardrail_result)
            yield  # pragma: no cover

        def cancel(self):
            return None

    monkeypatch.setattr("agents.Runner.run_streamed", staticmethod(lambda **_: _FakeRunResult()))

    stream = agent.get_response_stream(message="Need help", agency_context=ctx)

    events: list[object] = []
    async for ev in stream:
        events.append(ev)

    assert prune_invocations == 1
    assert ctx.thread_manager.get_all_messages() == pruned_history
    assert any(getattr(ev, "name", None) == "message_output_created" for ev in events)

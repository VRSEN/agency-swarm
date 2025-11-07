from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agency_swarm import (
    GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    ThreadManager,
)
from agency_swarm.agent.core import AgencyContext


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
    agent.throw_input_guardrail_error = True

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
    async for ev in agent.get_response_stream(message="Hello", agency_context=ctx):
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
    agent.throw_input_guardrail_error = False

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
    """When throw_input_guardrail_error=True, no assistant messages should persist."""
    agent = minimal_agent
    agent.throw_input_guardrail_error = True

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

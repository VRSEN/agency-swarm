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
    guardrail_result = type(
        "_OutputGuardrailResult",
        (),
        {
            "output": type("_Output", (), {"output_info": "fix it"})(),
            "guardrail": object(),
        },
    )()
    mock_runner_run.side_effect = [
        OutputGuardrailTripwireTriggered(guardrail_result),
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

    ctx = AgencyContext(agency_instance=None, thread_manager=ThreadManager(), subagents={})

    calls = {"n": 0}

    def fake_run_streamed(**kwargs):
        calls["n"] += 1
        guardrail_result = type(
            "_InputGuardrailResult",
            (),
            {
                "output": GuardrailFunctionOutput(
                    output_info="Prefix your request with 'Task:'",
                    tripwire_triggered=True,
                ),
                "guardrail": object(),
            },
        )()
        raise InputGuardrailTripwireTriggered(guardrail_result)

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

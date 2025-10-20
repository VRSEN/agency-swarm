import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from agents.stream_events import RunItemStreamEvent

from agency_swarm import OutputGuardrailTripwireTriggered

from ._streaming_helpers import build_message_item, make_stream_result


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_streaming_handoff_updates_agent_switch_metadata(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    class HandoffItem:
        def __init__(self) -> None:
            self.type = "handoff_output_item"
            self.raw_item = {"output": json.dumps({"assistant": "ResponderAgent"})}
            self.id = "handoff-item"

        def to_input_item(self):
            return {"role": "assistant", "content": "Handoff occurred", "id": self.id}

    response_item = build_message_item("msg_after_handoff", "Responder output")

    mock_runner_run_streamed_patch.return_value = make_stream_result(
        [
            RunItemStreamEvent(
                name="handoff_occurred",
                item=HandoffItem(),
                type="run_item_stream_event",
            ),
            RunItemStreamEvent(
                name="message_output_created",
                item=response_item,
                type="run_item_stream_event",
            ),
        ],
        history_snapshot=[{"role": "assistant", "content": "Handoff occurred", "id": "handoff-item"}],
    )

    events = [event async for event in minimal_agent.get_response_stream("Initiate handoff")]

    handoff_event = next(event for event in events if getattr(event, "name", None) == "handoff_occurred")
    assert getattr(handoff_event, "agent", None) == "ResponderAgent"
    assert getattr(handoff_event, "agent_run_id", "").startswith("agent_run_")

    follow_up = next(event for event in events if getattr(event, "name", None) == "message_output_created")
    assert getattr(follow_up, "agent", None) == "ResponderAgent"

    persisted_messages = mock_thread_manager.get_all_messages()
    assert any(msg.get("agent") == "ResponderAgent" for msg in persisted_messages)


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_streaming_preserves_forwarded_subagent_events(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager, monkeypatch
):
    forwarded_event = SimpleNamespace(
        type="run_item_stream_event",
        item=None,
        agent="SubAgent",
        callerAgent="PrimaryAgent",
    )

    from agency_swarm.streaming import StreamingContext as RealStreamingContext

    class ForwardingContext(RealStreamingContext):
        def __init__(self) -> None:
            super().__init__()
            forwarded_event._forwarded = True
            self.event_queue.put_nowait(forwarded_event)
            self.event_queue.put_nowait(None)

    monkeypatch.setattr("agency_swarm.streaming.StreamingContext", ForwardingContext)

    response_item = build_message_item("msg_primary", "Primary agent reply")

    mock_runner_run_streamed_patch.return_value = make_stream_result(
        [
            RunItemStreamEvent(
                name="message_output_created",
                item=response_item,
                type="run_item_stream_event",
            )
        ],
        delay_first_event=True,
    )

    events = [event async for event in minimal_agent.get_response_stream("Trigger forwarded event")]

    forwarded = next(ev for ev in events if getattr(ev, "agent", None) == "SubAgent")
    assert getattr(forwarded, "_forwarded", False) is True
    assert getattr(forwarded, "callerAgent", None) == "PrimaryAgent"

    persisted_messages = mock_thread_manager.get_all_messages()
    assert all(msg.get("agent") != "SubAgent" for msg in persisted_messages)


@pytest.mark.asyncio
async def test_streaming_retries_after_output_guardrail(monkeypatch, minimal_agent, mock_thread_manager):
    minimal_agent.validation_attempts = 1

    attempts: list[list[dict]] = []
    guidance_history = [{"role": "system", "content": "Guardrail guidance"}]

    class _OutputGuardrailResult:
        def __init__(self) -> None:
            self.output = SimpleNamespace(output_info="Guardrail guidance")
            self.guardrail = object()

    guardrail_exception = OutputGuardrailTripwireTriggered(_OutputGuardrailResult())
    response_item = build_message_item("msg_after_retry", "Recovered output")

    def fake_perform_streamed_run(
        *,
        agent,
        history_for_runner,
        master_context_for_run,
        hooks_override,
        run_config_override,
        kwargs,
    ):
        attempts.append(list(history_for_runner))
        if len(attempts) == 1:
            raise guardrail_exception
        return make_stream_result(
            [
                RunItemStreamEvent(
                    name="message_output_created",
                    item=response_item,
                    type="run_item_stream_event",
                )
            ],
            history_snapshot=history_for_runner,
            final_output="Recovered output",
        )

    def fake_append_guardrail_feedback(
        *,
        agent,
        agency_context,
        sender_name,
        parent_run_id,
        run_trace_id,
        current_agent_run_id,
        exception,
        include_assistant,
    ):
        return list(guidance_history)

    monkeypatch.setattr("agency_swarm.agent.execution_streaming.perform_streamed_run", fake_perform_streamed_run)
    monkeypatch.setattr(
        "agency_swarm.agent.execution_streaming.append_guardrail_feedback", fake_append_guardrail_feedback
    )

    stream = minimal_agent.get_response_stream("Trigger guardrail retry")
    events = [event async for event in stream]
    result = await stream.wait_final_result()

    assert len(attempts) == 2 and attempts[1] == guidance_history
    assert any(isinstance(ev, RunItemStreamEvent) for ev in events)
    assert result is not None and result.final_output == "Recovered output"

    persisted_messages = mock_thread_manager.get_all_messages()
    assert any(msg.get("id") == "msg_after_retry" for msg in persisted_messages)

"""EveryNToolCalls counters must persist across run boundaries within one conversation
thread: a normal multi-turn Agency conversation should accumulate tool-call counts across
`get_response()` calls instead of restarting at zero on every turn, while a genuinely new
conversation thread must still start at zero. See docs/core-framework/agents/advanced-configuration.mdx.
"""

from __future__ import annotations

import copy
from collections.abc import AsyncIterator

import pytest
from agents import ModelSettings, Tool, TResponseInputItem
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff as SDKHandoff
from agents.items import ModelResponse, TResponseStreamEvent
from agents.models.interface import Model, ModelTracing
from openai.types.responses.response_prompt_param import ResponsePromptParam

from agency_swarm import Agency, Agent, EveryNToolCalls
from agency_swarm.agent.system_reminder_state import _RunReminderState
from tests.deterministic_model import _build_message_response, _build_tool_call_response, _stream_text_events
from tests.test_agent_modules.test_system_reminders_review_regressions import (
    _contains,
    _local_tool,
    _reminder_hooks,
    _run_context,
    _ToolThenAnswerModel,
)


class _NToolCallsPerTurnModel(Model):
    """Call the tool `threshold` times per top-level user turn, then answer.

    Counts tool outputs seen since the most recent user message, mirroring how a real
    tool-heavy agent works turn by turn.
    """

    def __init__(self, threshold: int) -> None:
        self.model = "test-n-tool-calls-per-turn"
        self.threshold = threshold
        self.recorded_inputs: list[list[TResponseInputItem]] = []

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[SDKHandoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> ModelResponse:
        if not isinstance(input, list):
            raise TypeError("This test model expects structured input items.")

        self.recorded_inputs.append(copy.deepcopy(input))
        tool_outputs = 0
        for item in reversed(input):
            if isinstance(item, dict) and item.get("role") == "user":
                break
            if isinstance(item, dict) and item.get("type") in {"function_call_output", "tool_call_output_item"}:
                tool_outputs += 1

        if tool_outputs < self.threshold:
            return _build_tool_call_response(tools[0].name, {})
        return _build_message_response("done", self.model)

    def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[SDKHandoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        return _stream_text_events("done", self.model)


@pytest.mark.asyncio
async def test_every_n_tool_calls_fires_from_cumulative_count_across_turns() -> None:
    """The documented example: EveryNToolCalls(15, ...) with 7 tool calls per turn across
    3 turns (21 total) must fire once cumulative tool calls reach 15, in the 3rd turn.

    Before this fix, every turn restarted its count at zero, so 7 < 15 every time and the
    reminder never fired for a normal multi-turn conversational agent.
    """
    model = _NToolCallsPerTurnModel(threshold=7)
    agent = Agent(
        name="ReminderAgent",
        instructions="Use the tool until the task is done.",
        model=model,
        model_settings=ModelSettings(temperature=0.0),
        tools=[_local_tool],
        system_reminders=[EveryNToolCalls(15, "Checkpoint reminder")],
    )
    agency = Agency(agent)

    await agency.get_response("Handle task-1")
    await agency.get_response("Handle task-2")
    await agency.get_response("Handle task-3")

    # 3 turns x 8 model calls each (7 tool calls + 1 final answer) = 24 calls total.
    assert len(model.recorded_inputs) == 24
    fired_at = [index for index, items in enumerate(model.recorded_inputs) if _contains(items, "Checkpoint reminder")]

    # Cumulative tool calls cross 15 right after the 1st tool call of turn 3 (7+7+1=15),
    # which is model call index 17 (turn 3 starts at index 16; call 16 has 0 outputs
    # so far this turn, call 17 sees the reminder injected after that tool call ran).
    assert fired_at == [17]


@pytest.mark.asyncio
async def test_every_n_tool_calls_new_agency_thread_starts_at_zero() -> None:
    """A brand-new Agency (a genuinely new conversation thread) must not inherit another
    thread's tool-call count, even when it wraps the exact same Agent instance."""
    agent = Agent(
        name="SharedAgent",
        instructions="x",
        tools=[_local_tool],
        system_reminders=[EveryNToolCalls(2, "Checkpoint reminder")],
    )

    thread_a = Agency(agent)
    model_a1 = _ToolThenAnswerModel()
    agent.model = model_a1
    await thread_a.get_response("Handle task-1")
    # Thread A's count is now 1/2; not yet due.
    assert not _contains(model_a1.inputs[-1], "Checkpoint reminder")

    # A different Agency wrapping the same Agent is a different conversation thread.
    # If the count leaked from thread A, this single tool call would push it to 2/2 and fire.
    thread_b = Agency(agent)
    model_b1 = _ToolThenAnswerModel()
    agent.model = model_b1
    await thread_b.get_response("Handle task-1")
    assert not _contains(model_b1.inputs[-1], "Checkpoint reminder")

    # Thread A's own count did genuinely persist: its second turn now crosses the threshold.
    model_a2 = _ToolThenAnswerModel()
    agent.model = model_a2
    await thread_a.get_response("Handle task-2")
    assert _contains(model_a2.inputs[-1], "Checkpoint reminder")


def test_state_from_payload_clamps_hostile_tool_call_counts() -> None:
    """A hand-crafted RunState payload must not seed a huge or negative count.

    `_advance_tool_call_counters` never produces a count outside `[0, n)`, but decoded
    JSON is untrusted input; the index was already bounds-checked, but the value was not.
    """
    agent = Agent(name="Hostile", instructions="x", system_reminders=[EveryNToolCalls(5, "Checkpoint")])
    hooks = _reminder_hooks(agent)

    huge_state = hooks._state_from_payload({"tool_call_counts": {"0": 10**9}})
    negative_state = hooks._state_from_payload({"tool_call_counts": {"0": -(10**9)}})

    assert huge_state.tool_call_counts == {0: 4}  # clamped to n - 1
    assert negative_state.tool_call_counts == {0: 0}  # clamped to 0


def test_state_payload_round_trips_legitimate_tool_call_counts() -> None:
    """Clamping must not alter a count that was already inside the valid range."""
    agent = Agent(name="Legit", instructions="x", system_reminders=[EveryNToolCalls(5, "Checkpoint")])
    hooks = _reminder_hooks(agent)

    original = _RunReminderState(tool_call_counts={0: 3})
    payload = hooks._state_to_payload(original, hook_index=0)
    restored = hooks._state_from_payload(payload)

    assert restored.tool_call_counts == {0: 3}


@pytest.mark.asyncio
async def test_hostile_tool_call_count_does_not_corrupt_persistent_thread_state() -> None:
    """A hostile restored count must not survive into cross-run thread persistence.

    Persisting counts across runs means a value restored into one run's state can now
    outlive that run: `_advance_tool_call_counters` writes it into the per-thread store
    on every tool call. If the value weren't clamped first, a hostile huge or negative
    count would corrupt the whole thread instead of just one run.
    """
    agent = Agent(
        name="HostileThread",
        instructions="x",
        tools=[_local_tool],
        system_reminders=[EveryNToolCalls(5, "Checkpoint reminder")],
    )
    hooks = _reminder_hooks(agent)

    # A hostile negative count, already clamped by _state_from_payload, seeded into a run
    # that carries a real (thread-identifying) MasterContext.
    negative_context = _run_context(agent, "run-negative")
    run_key = hooks._resolve_run_key(negative_context)
    hooks._run_state[run_key] = hooks._state_from_payload({"tool_call_counts": {"0": -(10**9)}})

    await hooks.on_tool_end(negative_context, agent, _local_tool, "ok")

    thread_key = hooks._thread_key(negative_context)
    assert hooks._thread_tool_call_counts[thread_key] == {0: 1}

    # A hostile huge positive count behaves like a legitimate value at the threshold.
    huge_context = _run_context(agent, "run-huge")
    huge_run_key = hooks._resolve_run_key(huge_context)
    hooks._run_state[huge_run_key] = hooks._state_from_payload({"tool_call_counts": {"0": 10**9}})

    await hooks.on_tool_end(huge_context, agent, _local_tool, "ok")

    huge_thread_key = hooks._thread_key(huge_context)
    assert hooks._thread_tool_call_counts[huge_thread_key] == {0: 0}

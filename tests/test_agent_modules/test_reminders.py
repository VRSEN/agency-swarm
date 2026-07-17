from __future__ import annotations

import copy
from collections.abc import AsyncIterator

import pytest
from agents import (
    AgentHookContext,
    AgentHooks,
    ModelSettings,
    RunContextWrapper,
    Tool,
    TResponseInputItem,
    function_tool,
)
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff as RawSDKHandoff
from agents.items import ModelResponse, TResponseStreamEvent
from agents.models.interface import Model, ModelTracing
from openai.types.responses.response_prompt_param import ResponsePromptParam

from agency_swarm import AfterEveryUserMessage, Agency, Agent, EveryNToolCalls, MasterContext
from agency_swarm.tools import Handoff
from tests.deterministic_model import (
    DeterministicModel,
    _build_message_response,
    _build_tool_call_response,
    _stream_text_events,
)


def test_every_n_tool_calls_rejects_non_positive_threshold() -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        EveryNToolCalls(0, "Checkpoint reminder")


class _TrackingHook(AgentHooks[MasterContext]):
    def __init__(self) -> None:
        self.started = False

    async def on_start(self, context: AgentHookContext[MasterContext], agent: Agent) -> None:
        self.started = True


class _RecordingDeterministicModel(DeterministicModel):
    def __init__(self, default_response: str = "OK") -> None:
        super().__init__(default_response=default_response)
        self.recorded_inputs: list[list[TResponseInputItem]] = []

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[RawSDKHandoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> ModelResponse:
        if isinstance(input, list):
            self.recorded_inputs.append(copy.deepcopy(input))
        return await super().get_response(
            system_instructions,
            input,
            model_settings,
            tools,
            output_schema,
            handoffs,
            tracing,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        )


class _TwoToolCallsModel(Model):
    def __init__(self) -> None:
        self.model = "test-two-tools"
        self.recorded_inputs: list[list[TResponseInputItem]] = []

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[RawSDKHandoff],
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
        if tool_outputs < 2:
            return _build_tool_call_response(tools[0].name, {})
        return _build_message_response("done", self.model)

    def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[RawSDKHandoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        return _stream_text_events("done", self.model)


@function_tool
async def inspect_follow_up(ctx: RunContextWrapper[MasterContext]) -> str:
    """Return the stored follow-up for reminder tests."""
    follow_up = ctx.context.user_context.get("follow_up", "none")
    return f"Follow-up: {follow_up}"


def _extract_text(item: TResponseInputItem) -> str | None:
    if not isinstance(item, dict):
        return None
    content = item.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                text_value = part.get("text")
                if isinstance(text_value, str):
                    parts.append(text_value)
        if parts:
            return "".join(parts)
    return None


def _contains_text(items: list[TResponseInputItem], expected: str) -> bool:
    return any(expected in (_extract_text(item) or "") for item in items)


@pytest.mark.asyncio
async def test_system_reminders_compose_with_user_hooks() -> None:
    tracking_hook = _TrackingHook()
    model = _RecordingDeterministicModel()
    agent = Agent(
        name="ReminderAgent",
        instructions="Answer briefly.",
        hooks=tracking_hook,
        model=model,
        model_settings=ModelSettings(temperature=0.0),
        system_reminders=[
            AfterEveryUserMessage(lambda ctx, _agent: f"Follow-up: {ctx.context.user_context['follow_up']}")
        ],
    )
    agency = Agency(agent, user_context={"follow_up": "Send the renewal deck"})

    await agency.get_response("What should I do next?")

    assert tracking_hook.started is True
    assert _contains_text(model.recorded_inputs[0], "Follow-up: Send the renewal deck")


@pytest.mark.asyncio
async def test_after_every_user_message_is_transient_in_thread_history() -> None:
    model = _RecordingDeterministicModel(default_response="Actionable reply")
    agent = Agent(
        name="ReminderAgent",
        instructions="Answer briefly.",
        model=model,
        model_settings=ModelSettings(temperature=0.0),
        system_reminders=[
            AfterEveryUserMessage(lambda ctx, _agent: f"Stored follow-up: {ctx.context.user_context['follow_up']}")
        ],
    )
    agency = Agency(agent, user_context={"follow_up": "Send the renewal deck"})

    await agency.get_response("What follow-up is open?")

    assert _contains_text(model.recorded_inputs[0], "Stored follow-up: Send the renewal deck")
    history = agency.thread_manager.get_all_messages()
    assert [message["role"] for message in history] == ["user", "assistant"]
    assert not any("Stored follow-up:" in str(message.get("content", "")) for message in history)


@pytest.mark.asyncio
async def test_every_n_tool_calls_injects_on_next_llm_call_and_resets() -> None:
    model = _TwoToolCallsModel()
    agent = Agent(
        name="ReminderAgent",
        instructions="Use the tool until the task is done.",
        model=model,
        model_settings=ModelSettings(temperature=0.0),
        tools=[inspect_follow_up],
        system_reminders=[EveryNToolCalls(2, "Checkpoint reminder")],
    )
    agency = Agency(agent, user_context={"follow_up": "Send the renewal deck"})

    await agency.get_response("Handle task-1")
    await agency.get_response("Handle task-2")

    assert len(model.recorded_inputs) == 6
    assert not _contains_text(model.recorded_inputs[0], "Checkpoint reminder")
    assert not _contains_text(model.recorded_inputs[1], "Checkpoint reminder")
    assert _contains_text(model.recorded_inputs[2], "Checkpoint reminder")
    assert not _contains_text(model.recorded_inputs[3], "Checkpoint reminder")
    assert not _contains_text(model.recorded_inputs[4], "Checkpoint reminder")
    assert _contains_text(model.recorded_inputs[5], "Checkpoint reminder")


@pytest.mark.asyncio
async def test_after_every_user_message_skips_send_message_recipients() -> None:
    coordinator = Agent(
        name="Coordinator",
        instructions="Delegate work to Worker when asked.",
        model=DeterministicModel(),
        model_settings=ModelSettings(temperature=0.0),
    )
    worker_model = _RecordingDeterministicModel(default_response="Worker done")
    worker = Agent(
        name="Worker",
        instructions="Handle delegated tasks.",
        model=worker_model,
        model_settings=ModelSettings(temperature=0.0),
        system_reminders=[AfterEveryUserMessage("Nested reminder")],
    )
    agency = Agency(coordinator, worker, communication_flows=[coordinator > worker])

    await agency.get_response("Ask Worker to handle task-123", recipient_agent=coordinator)

    assert worker_model.recorded_inputs
    assert not _contains_text(worker_model.recorded_inputs[0], "Nested reminder")


@pytest.mark.asyncio
async def test_after_every_user_message_skips_handoff_recipients() -> None:
    coordinator = Agent(
        name="Coordinator",
        instructions="Hand off work to Worker when asked.",
        model=DeterministicModel(),
        model_settings=ModelSettings(temperature=0.0),
    )
    worker_model = _RecordingDeterministicModel(default_response="Worker done")
    worker = Agent(
        name="Worker",
        instructions="Handle handed-off tasks.",
        model=worker_model,
        model_settings=ModelSettings(temperature=0.0),
        system_reminders=[AfterEveryUserMessage("Handoff reminder should not appear")],
    )
    agency = Agency(coordinator, worker, communication_flows=[(coordinator > worker, Handoff)])

    await agency.get_response("Transfer to Worker and handle task-123", recipient_agent=coordinator)

    assert worker_model.recorded_inputs
    assert not _contains_text(worker_model.recorded_inputs[0], "Handoff reminder should not appear")

from __future__ import annotations

import copy
import uuid
from collections.abc import AsyncIterator

import pytest
from agents import (
    AgentHookContext,
    AgentHooks,
    ModelSettings,
    RunContextWrapper,
    Tool,
    TResponseInputItem,
    WebSearchTool,
    function_tool,
)
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff as SDKHandoff
from agents.items import ModelResponse, TResponseStreamEvent
from agents.models.interface import Model, ModelTracing
from agents.usage import Usage
from openai.types.responses import ResponseFunctionWebSearch
from openai.types.responses.response_function_web_search import ActionSearch
from openai.types.responses.response_prompt_param import ResponsePromptParam

from agency_swarm import AfterEveryUserMessage, Agency, Agent, EveryNToolCalls, MasterContext
from agency_swarm.tools import Handoff
from tests.deterministic_model import (
    DeterministicModel,
    _build_message_response,
    _build_tool_call_response,
    _stream_text_events,
)


class _RecordingHook(AgentHooks[MasterContext]):
    def __init__(self) -> None:
        self.started = False
        self.llm_inputs: list[list[TResponseInputItem]] = []

    async def on_start(self, context: AgentHookContext[MasterContext], agent: Agent) -> None:
        self.started = True

    async def on_llm_start(
        self,
        context: RunContextWrapper[MasterContext],
        agent: Agent,
        system_prompt: str | None,
        input_items: list[TResponseInputItem],
    ) -> None:
        self.llm_inputs.append(copy.deepcopy(input_items))


class _RecordingModel(DeterministicModel):
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
        handoffs: list[SDKHandoff],
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
        self.model = "test-two-tool-calls"
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
        handoffs: list[SDKHandoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        return _stream_text_events("done", self.model)


class _WebSearchThenAnswerModel(Model):
    """Emit one hosted web_search_call first, then a final message."""

    def __init__(self) -> None:
        self.model = "test-web-search"
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
        if len(self.recorded_inputs) == 1:
            web_search_call = ResponseFunctionWebSearch(
                id=f"ws_{uuid.uuid4().hex}",
                action=ActionSearch(query="open follow-ups", type="search"),
                status="completed",
                type="web_search_call",
            )
            return ModelResponse(output=[web_search_call], usage=Usage(), response_id=f"resp_{uuid.uuid4().hex}")
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


@function_tool
async def check_task_state(ctx: RunContextWrapper[MasterContext]) -> str:
    """Return a deterministic tool output for system reminder tests."""
    return ctx.context.user_context.get("task_state", "ready")


def _extract_text(item: TResponseInputItem) -> str | None:
    if not isinstance(item, dict):
        return None
    content = item.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        return "".join(part for part in parts if isinstance(part, str)) or None
    return None


def _contains_text(items: list[TResponseInputItem], expected: str) -> bool:
    return any(expected in (_extract_text(item) or "") for item in items)


def test_system_reminders_validate_config() -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        EveryNToolCalls(0, "Checkpoint reminder")

    with pytest.raises(TypeError, match="must be an integer"):
        EveryNToolCalls(True, "Checkpoint reminder")

    with pytest.raises(ValueError, match="non-empty"):
        Agent(name="BadReminder", instructions="Answer briefly.", system_reminders=[""])

    with pytest.raises(TypeError, match="strings, callables, or SystemReminder"):
        Agent(name="BadReminder", instructions="Answer briefly.", system_reminders=[object()])


def test_plain_string_system_reminder_uses_user_message_trigger() -> None:
    agent = Agent(
        name="ReminderAgent",
        instructions="Answer briefly.",
        model=DeterministicModel(),
        system_reminders="Before replying, end with one clear next step.",
    )

    assert len(agent.system_reminders) == 1
    assert isinstance(agent.system_reminders[0], AfterEveryUserMessage)

    callable_agent = Agent(
        name="CallableReminderAgent",
        instructions="Answer briefly.",
        model=DeterministicModel(),
        system_reminders=lambda _ctx, _agent: "Callable reminder",
    )

    assert len(callable_agent.system_reminders) == 1
    assert isinstance(callable_agent.system_reminders[0], AfterEveryUserMessage)


@pytest.mark.asyncio
async def test_system_reminders_compose_with_user_hooks() -> None:
    hook = _RecordingHook()
    model = _RecordingModel()
    agent = Agent(
        name="ReminderAgent",
        instructions="Answer briefly.",
        hooks=hook,
        model=model,
        model_settings=ModelSettings(temperature=0.0),
        system_reminders="Before replying, end with one clear next step.",
    )
    agency = Agency(agent)

    await agency.get_response("What should I do next?")

    assert hook.started is True
    assert _contains_text(hook.llm_inputs[0], "Before replying, end with one clear next step.")
    assert _contains_text(model.recorded_inputs[0], "Before replying, end with one clear next step.")


@pytest.mark.asyncio
async def test_after_every_user_message_is_transient_in_thread_history() -> None:
    model = _RecordingModel(default_response="Actionable reply")
    agent = Agent(
        name="ReminderAgent",
        instructions="Answer briefly.",
        model=model,
        model_settings=ModelSettings(temperature=0.0),
        system_reminders=[
            AfterEveryUserMessage(lambda ctx, _agent: f"Task state: {ctx.context.user_context['task_state']}")
        ],
    )
    agency = Agency(agent, user_context={"task_state": "ready"})

    await agency.get_response("What is next?")

    assert _contains_text(model.recorded_inputs[0], "Task state: ready")
    history = agency.thread_manager.get_all_messages()
    assert [message["role"] for message in history] == ["user", "assistant"]
    assert not any("Task state:" in str(message.get("content", "")) for message in history)


@pytest.mark.asyncio
async def test_every_n_tool_calls_injects_on_next_llm_call_and_resets() -> None:
    model = _TwoToolCallsModel()
    agent = Agent(
        name="ReminderAgent",
        instructions="Use the tool until the task is done.",
        model=model,
        model_settings=ModelSettings(temperature=0.0),
        tools=[check_task_state],
        system_reminders=[EveryNToolCalls(2, "Checkpoint reminder")],
    )
    agency = Agency(agent, user_context={"task_state": "ready"})

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
async def test_every_n_tool_calls_counts_hosted_tool_calls() -> None:
    model = _WebSearchThenAnswerModel()
    agent = Agent(
        name="ReminderAgent",
        instructions="Search the web, then answer.",
        model=model,
        model_settings=ModelSettings(temperature=0.0),
        tools=[WebSearchTool()],
        system_reminders=[EveryNToolCalls(1, "Checkpoint reminder")],
    )
    agency = Agency(agent)

    await agency.get_response("Handle task-1")

    assert len(model.recorded_inputs) == 2
    assert not _contains_text(model.recorded_inputs[0], "Checkpoint reminder")
    assert _contains_text(model.recorded_inputs[1], "Checkpoint reminder")


@pytest.mark.asyncio
async def test_after_every_user_message_skips_send_message_recipients() -> None:
    coordinator = Agent(
        name="Coordinator",
        instructions="Delegate work to Worker when asked.",
        model=DeterministicModel(),
        model_settings=ModelSettings(temperature=0.0),
    )
    worker_model = _RecordingModel(default_response="Worker done")
    worker = Agent(
        name="Worker",
        instructions="Handle delegated tasks.",
        model=worker_model,
        model_settings=ModelSettings(temperature=0.0),
        system_reminders="Nested reminder",
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
    worker_model = _RecordingModel(default_response="Worker done")
    worker = Agent(
        name="Worker",
        instructions="Handle handed-off tasks.",
        model=worker_model,
        model_settings=ModelSettings(temperature=0.0),
        system_reminders="Handoff reminder should not appear",
    )
    agency = Agency(coordinator, worker, communication_flows=[(coordinator > worker, Handoff)])

    await agency.get_response("Transfer to Worker and handle task-123", recipient_agent=coordinator)

    assert worker_model.recorded_inputs
    assert not _contains_text(worker_model.recorded_inputs[0], "Handoff reminder should not appear")

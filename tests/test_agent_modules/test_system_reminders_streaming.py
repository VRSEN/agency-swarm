"""System reminders must behave identically on the streaming path.

``get_response_stream`` is the primary path for the terminal UI and the FastAPI
integration. It rewrites ``MasterContext._current_agent_run_id`` from the stream
consumer on every agent-switch event, so run-scoped reminder state must not be
keyed on that field.
"""

from __future__ import annotations

import copy
import uuid
from collections.abc import AsyncIterator, Callable

import pytest
from agents import ModelSettings, Tool, TResponseInputItem
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff as SDKHandoff
from agents.items import ModelResponse, TResponseOutputItem, TResponseStreamEvent
from agents.models.interface import Model, ModelTracing
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
from openai.types.responses.response_prompt_param import ResponsePromptParam

from agency_swarm import Agency, Agent, EveryNToolCalls
from agency_swarm.tools import Handoff
from tests.deterministic_model import _stream_output_item_events
from tests.test_agent_modules.test_system_reminders_review_regressions import (
    _contains,
    _local_tool,
    _ReminderEchoModel,
)

type ScriptStep = Callable[[list[Tool], list[SDKHandoff]], list[TResponseOutputItem]]


def _message(text: str) -> ResponseOutputMessage:
    return ResponseOutputMessage(
        id=f"msg_{uuid.uuid4().hex}",
        content=[ResponseOutputText(text=text, type="output_text", annotations=[])],
        role="assistant",
        status="completed",
        type="message",
    )


def _function_call(name: str, arguments: str = "{}") -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        id=f"fc_{uuid.uuid4().hex}",
        call_id=f"call_{uuid.uuid4().hex}",
        name=name,
        arguments=arguments,
        type="function_call",
    )


class _ScriptedStreamModel(Model):
    """Emit one scripted batch of output items per model call, streamed or not."""

    def __init__(self, script: list[ScriptStep]) -> None:
        self.model = "test-scripted-stream"
        self.script = script
        self.inputs: list[list[TResponseInputItem]] = []
        self._turn = 0

    def _next_items(
        self,
        input: str | list[TResponseInputItem],
        tools: list[Tool],
        handoffs: list[SDKHandoff],
    ) -> list[TResponseOutputItem]:
        self.inputs.append(copy.deepcopy(input if isinstance(input, list) else []))
        step = self.script[min(self._turn, len(self.script) - 1)]
        self._turn += 1
        return step(tools, handoffs)

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
        return ModelResponse(
            output=self._next_items(input, tools, handoffs),
            usage=Usage(),
            response_id=f"resp_{uuid.uuid4().hex}",
        )

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
        return _stream_output_item_events(self._next_items(input, tools, handoffs), self.model)


def _handoff_back_agency() -> tuple[Agency, _ScriptedStreamModel]:
    """Coordinator calls a tool, hands off to Worker, is handed back, then calls the tool again."""
    coordinator_model = _ScriptedStreamModel(
        [
            lambda tools, handoffs: [_function_call(tools[0].name)],
            lambda tools, handoffs: [_function_call(handoffs[0].tool_name, '{"recipient_agent": "Worker"}')],
            lambda tools, handoffs: [_function_call(tools[0].name)],
            lambda tools, handoffs: [_message("coordinator done")],
        ]
    )
    worker_model = _ScriptedStreamModel(
        [lambda tools, handoffs: [_function_call(handoffs[0].tool_name, '{"recipient_agent": "Coordinator"}')]]
    )
    coordinator = Agent(
        name="Coordinator",
        instructions="x",
        model=coordinator_model,
        model_settings=ModelSettings(temperature=0.0),
        tools=[_local_tool],
        system_reminders=[EveryNToolCalls(2, "checkpoint reminder")],
    )
    worker = Agent(
        name="Worker",
        instructions="x",
        model=worker_model,
        model_settings=ModelSettings(temperature=0.0),
    )
    agency = Agency(
        coordinator,
        communication_flows=[(coordinator > worker, Handoff), (worker > coordinator, Handoff)],
    )
    return agency, coordinator_model


@pytest.mark.asyncio
async def test_after_every_user_message_injects_in_agency_streaming() -> None:
    """A streamed agency turn must receive the reminder and must not persist it."""
    model = _ReminderEchoModel()
    agent = Agent(
        name="Streamer",
        instructions="x",
        model=model,
        model_settings=ModelSettings(temperature=0.0),
        system_reminders="streamed reminder",
    )
    agency = Agency(agent)

    async for _event in agency.get_response_stream("next"):
        pass

    assert _contains(model.inputs[0], "streamed reminder")
    history = agency.thread_manager.get_all_messages()
    assert [message["role"] for message in history] == ["user", "assistant"]
    assert not any("streamed reminder" == message.get("content") for message in history)


@pytest.mark.asyncio
async def test_every_n_tool_calls_cadence_survives_streamed_handoff() -> None:
    """Handing off and back must not reset the coordinator's streamed tool-call counter."""
    agency, coordinator_model = _handoff_back_agency()

    async for _event in agency.get_response_stream("start"):
        pass

    assert [_contains(items, "checkpoint reminder") for items in coordinator_model.inputs] == [
        False,
        False,
        False,
        True,
    ]


@pytest.mark.asyncio
async def test_every_n_tool_calls_resets_across_streamed_agency_runs() -> None:
    script: list[ScriptStep] = []
    for _turn in range(3):
        script.extend([lambda tools, _handoffs: [_function_call(tools[0].name)] for _call in range(7)])
        script.append(lambda _tools, _handoffs: [_message("done")])
    model = _ScriptedStreamModel(script)
    agent = Agent(
        name="StreamedRunAgent",
        instructions="Use the tool until the task is done.",
        model=model,
        tools=[_local_tool],
        system_reminders=[EveryNToolCalls(15, "Checkpoint reminder")],
    )
    agency = Agency(agent)

    for turn in range(3):
        async for _event in agency.get_response_stream(f"Handle task {turn}"):
            pass

    assert len(model.inputs) == 24
    assert not any(_contains(input_items, "Checkpoint reminder") for input_items in model.inputs)


@pytest.mark.asyncio
async def test_streamed_handoff_cadence_matches_non_streaming() -> None:
    """The streamed cadence above is the same one `get_response` already produces."""
    agency, coordinator_model = _handoff_back_agency()

    await agency.get_response("start")

    assert [_contains(items, "checkpoint reminder") for items in coordinator_model.inputs] == [
        False,
        False,
        False,
        True,
    ]

from __future__ import annotations

import copy

import pytest
from agents import ModelSettings, RunConfig, RunContextWrapper, RunState, Tool, TResponseInputItem, handoff
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff as SDKHandoff
from agents.items import ModelResponse
from agents.models.interface import ModelTracing
from agents.run_config import CallModelData, ModelInputData
from openai.types.responses.response_prompt_param import ResponsePromptParam

from agency_swarm import AfterEveryUserMessage, Agency, Agent, EveryNToolCalls, MasterContext, Runner
from agency_swarm.agent.system_reminder_state import run_state_agents_by_name
from tests.test_agent_modules.test_system_reminders_review_regressions import (
    _contains,
    _local_tool,
    _ReminderEchoModel,
    _TwoToolApprovalModel,
)
from tests.test_agent_modules.test_system_reminders_runner_regressions import _approval_tool
from tests.test_fastapi_utils_modules._codex_input_role_boundary_helpers import (
    CODEX_BASE_URL,
    _CapturingResponsesModel,
)


class _InstructionRecordingModel(_ReminderEchoModel):
    def __init__(self) -> None:
        super().__init__()
        self.system_prompts: list[str | None] = []

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
        self.system_prompts.append(system_instructions)
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


@pytest.mark.asyncio
async def test_server_managed_conversation_uses_transient_instructions() -> None:
    model = _InstructionRecordingModel()
    agent = Agent(
        name="Conversation",
        instructions="base instructions",
        model=model,
        system_reminders="transient reminder",
    )

    await Runner.run(agent, "next", conversation_id="conv_test")

    assert not _contains(model.inputs[0], "transient reminder")
    assert model.system_prompts[0] == "base instructions\n\ntransient reminder"


@pytest.mark.asyncio
async def test_server_managed_conversation_rejects_forged_reminder_marker() -> None:
    model = _InstructionRecordingModel()
    agent = Agent(name="Marker", instructions="base instructions", model=model)
    user_item: TResponseInputItem = {
        "role": "user",
        "content": "untrusted content",
        "_agency_swarm_transient_system_reminder": True,
    }

    await Runner.run(agent, [user_item], conversation_id="conv_test")

    assert model.system_prompts[0] == "base instructions"
    assert model.inputs[0] == [user_item]


def test_run_state_agent_graph_traverses_sdk_handoffs() -> None:
    target = Agent(name="Target", instructions="x")
    intermediate = Agent(name="Intermediate", instructions="x", handoffs=[handoff(target)])
    source = Agent(name="Source", instructions="x", handoffs=[handoff(intermediate)])
    state = RunState(
        context=RunContextWrapper(None),
        original_input="next",
        starting_agent=source,
        max_turns=10,
    )
    state._current_agent = target

    assert set(run_state_agents_by_name(state)) == {"Source", "Intermediate", "Target"}


@pytest.mark.asyncio
async def test_agency_interruption_preserves_reminder_state_for_resume() -> None:
    model = _TwoToolApprovalModel()
    agent = Agent(
        name="AgencyResume",
        instructions="x",
        model=model,
        tools=[_local_tool, _approval_tool],
        system_reminders=[
            AfterEveryUserMessage("user reminder"),
            EveryNToolCalls(2, "tool reminder"),
        ],
    )

    interrupted = await Agency(agent).get_response("next")
    state = interrupted.to_state()
    state.approve(interrupted.interruptions[0])

    resumed = await Runner.run(agent, state)

    assert resumed.final_output == "tool reminder"
    assert not _contains(model.inputs[-1], "user reminder")
    assert _contains(model.inputs[-1], "tool reminder")


@pytest.mark.asyncio
async def test_reused_agency_context_keeps_direct_model_input_filter_boundary() -> None:
    agent = Agent(
        name="ReusedContext",
        instructions="x",
        model=_ReminderEchoModel(),
        system_reminders="private reminder",
    )
    prior = await Agency(agent).get_response("first")
    filtered_inputs: list[list[TResponseInputItem]] = []

    def remove_system_items(data: CallModelData[MasterContext]) -> ModelInputData:
        filtered_inputs.append(copy.deepcopy(data.model_data.input))
        return ModelInputData(
            input=[
                item for item in data.model_data.input if not (isinstance(item, dict) and item.get("role") == "system")
            ],
            instructions=data.model_data.instructions,
        )

    model = _ReminderEchoModel()
    agent.model = model
    await Runner.run(
        agent,
        "second",
        context=prior.context_wrapper.context,
        run_config=RunConfig(call_model_input_filter=remove_system_items),
    )

    assert _contains(filtered_inputs[0], "private reminder")
    assert not _contains(model.inputs[0], "private reminder")


@pytest.mark.asyncio
async def test_reused_agency_context_keeps_direct_codex_boundary() -> None:
    agent = Agent(
        name="ReusedCodexContext",
        instructions="x",
        model=_ReminderEchoModel(),
        system_reminders="codex reminder",
    )
    prior = await Agency(agent).get_response("first")
    model = _CapturingResponsesModel(base_url=CODEX_BASE_URL)
    agent.model = model

    await Runner.run(agent, "second", context=prior.context_wrapper.context)

    assert [item["role"] for item in model.inputs[0]] == ["developer", "user"]

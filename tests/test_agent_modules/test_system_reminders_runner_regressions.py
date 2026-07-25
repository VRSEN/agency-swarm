from __future__ import annotations

import copy
import subprocess
import sys
from dataclasses import dataclass

import pytest
from agents import Agent as SDKAgent, ModelSettings, RunConfig, Tool, TResponseInputItem, function_tool
from agents.agent_output import AgentOutputSchemaBase
from agents.exceptions import AgentsException
from agents.handoffs import Handoff as SDKHandoff
from agents.items import ModelResponse
from agents.models.interface import ModelTracing
from agents.run import AgentRunner, get_default_agent_runner, set_default_agent_runner
from agents.run_config import CallModelData, ModelInputData
from openai.types.responses.response_prompt_param import ResponsePromptParam

from agency_swarm import AfterEveryUserMessage, Agency, Agent, EveryNToolCalls, MasterContext, Runner, SystemReminder
from agency_swarm.utils.thread import ThreadManager
from tests.deterministic_model import _build_tool_call_response
from tests.test_agent_modules.test_system_reminders_review_regressions import (
    _contains,
    _FailingModel,
    _HandoffModel,
    _local_tool,
    _reminder_hooks,
    _ReminderEchoModel,
    _ToolThenAnswerModel,
    _TwoToolApprovalModel,
)
from tests.test_fastapi_utils_modules._codex_input_role_boundary_helpers import (
    CODEX_BASE_URL,
    _CapturingResponsesModel,
)


@function_tool(needs_approval=True)
async def _approval_tool() -> str:
    """Return a deterministic approved tool result."""
    return "approved"


class _AgentToolModel(_ReminderEchoModel):
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
        if self.calls == 0:
            self.calls += 1
            self.inputs.append(copy.deepcopy(input if isinstance(input, list) else []))
            return _build_tool_call_response(tools[0].name, {"input": "nested request"})
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


class _ToolThenFailModel(_ReminderEchoModel):
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
        if self.calls == 0:
            self.calls += 1
            self.inputs.append(copy.deepcopy(input if isinstance(input, list) else []))
            return _build_tool_call_response(tools[0].name, {})
        raise RuntimeError("target failed")


@pytest.mark.asyncio
async def test_model_input_filter_can_remove_injected_reminders() -> None:
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
    agent = Agent(name="Filtered", instructions="x", model=model, system_reminders="private reminder")

    await Agency(agent).get_response(
        "next",
        run_config=RunConfig(call_model_input_filter=remove_system_items),
    )

    assert _contains(filtered_inputs[0], "private reminder")
    assert not _contains(model.inputs[0], "private reminder")


@pytest.mark.asyncio
async def test_direct_runner_model_input_filter_can_remove_injected_reminders() -> None:
    filtered_inputs: list[list[TResponseInputItem]] = []

    def remove_system_items(data: CallModelData[None]) -> ModelInputData:
        filtered_inputs.append(copy.deepcopy(data.model_data.input))
        return ModelInputData(
            input=[
                item for item in data.model_data.input if not (isinstance(item, dict) and item.get("role") == "system")
            ],
            instructions=data.model_data.instructions,
        )

    model = _ReminderEchoModel()
    agent = Agent(name="DirectFiltered", instructions="x", model=model, system_reminders="private reminder")

    await Runner.run(
        agent,
        "next",
        run_config=RunConfig(call_model_input_filter=remove_system_items),
    )

    assert _contains(filtered_inputs[0], "private reminder")
    assert not _contains(model.inputs[0], "private reminder")


@pytest.mark.asyncio
async def test_direct_runner_codex_rewrites_injected_reminder_role() -> None:
    model = _CapturingResponsesModel(base_url=CODEX_BASE_URL)
    agent = Agent(name="DirectCodex", instructions="x", model=model, system_reminders="Remember this")

    await Runner.run(agent, "next")

    assert [item["role"] for item in model.inputs[0]] == ["developer", "user"]


@pytest.mark.asyncio
async def test_direct_runner_boundary_survives_default_runner_replacement() -> None:
    previous_runner = get_default_agent_runner()
    set_default_agent_runner(AgentRunner())
    try:
        reminder_model = _ReminderEchoModel()
        reminder_agent = Agent(
            name="ReplacedRunner",
            instructions="x",
            model=reminder_model,
            system_reminders="still active",
        )
        context = MasterContext(
            thread_manager=ThreadManager(),
            agents={reminder_agent.name: reminder_agent},
            current_agent_name=reminder_agent.name,
        )
        reminder_result = await Runner.run(reminder_agent, "next", context=context)

        codex_model = _CapturingResponsesModel(base_url=CODEX_BASE_URL)
        codex_agent = Agent(
            name="ReplacedCodex",
            instructions="x",
            model=codex_model,
            system_reminders="Remember this",
        )
        await Runner.run(codex_agent, "next")
    finally:
        set_default_agent_runner(previous_runner)

    assert reminder_result.final_output == "still active"
    assert [item["role"] for item in codex_model.inputs[0]] == ["developer", "user"]


@pytest.mark.asyncio
async def test_system_reminders_support_direct_runner_without_context() -> None:
    model = _ReminderEchoModel()
    agent = Agent(name="Direct", instructions="x", model=model, system_reminders="direct reminder")

    result = await Runner.run(agent, "next")

    assert result.final_output == "direct reminder"


@pytest.mark.asyncio
async def test_system_reminders_support_direct_runner_with_master_context() -> None:
    model = _ReminderEchoModel()
    agent = Agent(name="DirectMaster", instructions="x", model=model, system_reminders="master reminder")
    context = MasterContext(
        thread_manager=ThreadManager(),
        agents={agent.name: agent},
        current_agent_name=agent.name,
    )

    result = await Runner.run(agent, "next", context=context)

    assert result.final_output == "master reminder"


@pytest.mark.asyncio
async def test_system_reminders_support_direct_streaming_runner_without_context() -> None:
    model = _ReminderEchoModel()
    agent = Agent(name="DirectStream", instructions="x", model=model, system_reminders="stream reminder")

    result = Runner.run_streamed(agent, "next")
    events = [event async for event in result.stream_events()]

    assert events
    assert result.final_output == "stream reminder"
    assert _reminder_hooks(agent)._run_state == {}


@pytest.mark.asyncio
async def test_direct_runner_reminder_does_not_fire_after_handoff() -> None:
    target_model = _ReminderEchoModel()
    target = Agent(
        name="Target",
        instructions="x",
        model=target_model,
        system_reminders="target reminder",
    )
    source = Agent(
        name="Source",
        instructions="x",
        model=_HandoffModel(),
        handoffs=[target],
    )

    result = await Runner.run(source, "next")

    assert result.final_output == "missing"
    assert not _contains(target_model.inputs[0], "target reminder")


@pytest.mark.asyncio
async def test_direct_runner_clears_source_reminder_state_after_handoff() -> None:
    target = Agent(name="CleanupTarget", instructions="x", model=_ReminderEchoModel())
    source = Agent(
        name="CleanupSource",
        instructions="x",
        model=_HandoffModel(),
        handoffs=[target],
        system_reminders="source reminder",
    )
    held_results = []

    for index in range(3):
        held_results.append(await Runner.run(source, f"next {index}"))
        assert _reminder_hooks(source)._run_state == {}

    assert len(held_results) == 3


@pytest.mark.asyncio
async def test_direct_runner_preserves_reminder_state_across_run_state_resume() -> None:
    model = _TwoToolApprovalModel()
    agent = Agent(
        name="Resume",
        instructions="x",
        model=model,
        tools=[_local_tool, _approval_tool],
        system_reminders=[
            AfterEveryUserMessage("user reminder"),
            EveryNToolCalls(2, "tool reminder"),
        ],
    )

    interrupted = await Runner.run(agent, "next")
    assert len(interrupted.interruptions) == 1
    state = interrupted.to_state()
    state.approve(interrupted.interruptions[0])

    resumed = await Runner.run(agent, state)

    assert resumed.final_output == "tool reminder"
    assert _contains(model.inputs[0], "user reminder")
    assert not _contains(model.inputs[-1], "user reminder")
    assert _contains(model.inputs[-1], "tool reminder")
    assert _reminder_hooks(agent)._run_state == {}


@pytest.mark.asyncio
async def test_direct_runner_preserves_reminder_state_across_serialized_resume() -> None:
    model = _TwoToolApprovalModel()
    agent = Agent(
        name="SerializedResume",
        instructions="x",
        model=model,
        tools=[_local_tool, _approval_tool],
        system_reminders=[
            AfterEveryUserMessage("user reminder"),
            EveryNToolCalls(2, "tool reminder"),
        ],
    )

    interrupted = await Runner.run(agent, "next")
    state = interrupted.to_state()
    restored_once = await type(state).from_json(agent, state.to_json())
    restored = await type(state).from_json(agent, restored_once.to_json())
    restored.approve(restored.get_interruptions()[0])

    resumed = await Runner.run(agent, restored)

    assert resumed.final_output == "tool reminder"
    assert not _contains(model.inputs[-1], "user reminder")
    assert _contains(model.inputs[-1], "tool reminder")
    assert _reminder_hooks(agent)._run_state == {}


@pytest.mark.asyncio
async def test_direct_runner_nested_agent_tool_reuses_outer_boundary() -> None:
    nested_model = _ReminderEchoModel()
    nested = Agent(
        name="Nested",
        instructions="x",
        model=nested_model,
        system_reminders="nested reminder",
    )
    outer = Agent(
        name="Outer",
        instructions="x",
        model=_AgentToolModel(),
        tools=[nested.as_tool("nested", "nested")],
    )

    await Runner.run(outer, "top-level user")

    assert nested_model.inputs
    assert not _contains(nested_model.inputs[0], "nested reminder")


@pytest.mark.asyncio
async def test_direct_runner_sdk_source_preserves_outer_boundary() -> None:
    target_model = _ReminderEchoModel()
    target = Agent(
        name="AgencyTarget",
        instructions="x",
        model=target_model,
        system_reminders="target reminder",
    )
    source = SDKAgent(
        name="SDKSource",
        instructions="x",
        model=_HandoffModel(),
        handoffs=[target],
    )

    await Runner.run(source, "top-level user")

    assert target_model.inputs
    assert not _contains(target_model.inputs[0], "target reminder")


@pytest.mark.asyncio
async def test_agency_cleans_unregistered_participant_reminder_state() -> None:
    target = Agent(
        name="ExternalTarget",
        instructions="x",
        model=_ToolThenFailModel(),
        tools=[_local_tool],
        system_reminders=[EveryNToolCalls(2, "checkpoint")],
    )
    source = Agent(
        name="Source",
        instructions="x",
        model=_HandoffModel(),
        handoffs=[target],
    )

    with pytest.raises(AgentsException):
        await Agency(source).get_response("go")

    assert _reminder_hooks(target)._run_state == {}


@pytest.mark.asyncio
async def test_direct_runner_cleans_tool_only_state_after_model_failure() -> None:
    agent = Agent(
        name="ToolOnlyFailure",
        instructions="x",
        model=_FailingModel(),
        system_reminders=[EveryNToolCalls(2, "tool reminder")],
    )

    with pytest.raises(RuntimeError, match="model failed"):
        await Runner.run(agent, "next")

    assert _reminder_hooks(agent)._run_state == {}


@pytest.mark.asyncio
async def test_callable_tool_reminder_receives_live_run_wrapper() -> None:
    model = _ToolThenAnswerModel()
    agent = Agent(
        name="LiveContext",
        instructions="x",
        model=model,
        tools=[_local_tool],
        system_reminders=[
            EveryNToolCalls(
                1,
                lambda ctx, _agent: f"usage={ctx.usage.requests};turn_input={len(ctx.turn_input)}",
            )
        ],
    )

    result = await Agency(agent).get_response("next")

    assert result.final_output == "usage=1;turn_input=1"


def test_bare_import_leaves_sdk_runner_unpatched() -> None:
    """Importing agency_swarm alone must not install the Runner boundary."""
    probe = (
        "import agency_swarm\n"
        "from agents import Runner\n"
        "print(getattr(Runner, '_agency_swarm_model_input_boundary_installed', False))\n"
    )
    # A subprocess is required: reminder-bearing agents in this session already installed the boundary.
    completed = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=False)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "False"


def test_reminder_agent_installs_runner_boundary_once() -> None:
    """The first reminder-bearing agent installs the boundary and later agents reuse it."""
    Agent(name="BoundaryInstaller", instructions="x", system_reminders="remember this")
    installed_run = Runner.__dict__["run"]

    assert getattr(Runner, "_agency_swarm_model_input_boundary_installed", False) is True

    Agent(name="BoundaryReuser", instructions="x", system_reminders="remember this too")

    assert Runner.__dict__["run"] is installed_run


def test_unsupported_system_reminder_subclass_is_rejected() -> None:
    @dataclass(frozen=True)
    class UnsupportedReminder(SystemReminder):
        message: str

        def __post_init__(self) -> None:
            self._validate_message()

    with pytest.raises(TypeError, match="unsupported system reminder type"):
        Agent(name="Unsupported", instructions="x", system_reminders=UnsupportedReminder("remember"))

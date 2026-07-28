from __future__ import annotations

import asyncio
import copy
import threading
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from agents import (
    ModelSettings,
    RunContextWrapper,
    Tool,
    TResponseInputItem,
    function_tool,
)
from agents.agent_output import AgentOutputSchemaBase
from agents.exceptions import AgentsException
from agents.handoffs import Handoff as SDKHandoff
from agents.items import ModelResponse, TResponseStreamEvent
from agents.models.interface import Model, ModelTracing
from agents.usage import Usage
from openai.types.responses import ResponseFunctionWebSearch
from openai.types.responses.response_function_web_search import ActionSearch
from openai.types.responses.response_prompt_param import ResponsePromptParam

from agency_swarm import Agency, Agent, EveryNToolCalls, MasterContext
from agency_swarm.agent.conversation_starters_cache import compute_starter_cache_fingerprint
from agency_swarm.agent.system_reminders import SystemReminderHooks
from agency_swarm.utils.thread import ThreadManager
from tests.deterministic_model import _build_message_response, _build_tool_call_response, _stream_text_events
from tests.test_fastapi_utils_modules._codex_input_role_boundary_helpers import (
    CODEX_BASE_URL,
    _CapturingResponsesModel,
)


class _ReminderEchoModel(Model):
    def __init__(self) -> None:
        self.model = "test-reminder-echo"
        self.calls = 0
        self.inputs: list[list[TResponseInputItem]] = []

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
        self.calls += 1
        items = input if isinstance(input, list) else []
        self.inputs.append(copy.deepcopy(items))
        reminder = next(
            (
                str(item.get("content"))
                for item in items
                if isinstance(item, dict) and item.get("role") in {"system", "developer"}
            ),
            "missing",
        )
        return _build_message_response(reminder, self.model)

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
        items = input if isinstance(input, list) else []
        self.inputs.append(copy.deepcopy(items))
        reminder = next(
            (
                str(item.get("content"))
                for item in items
                if isinstance(item, dict) and item.get("role") in {"system", "developer"}
            ),
            "missing",
        )
        return _stream_text_events(reminder, self.model)


class _FailingModel(_ReminderEchoModel):
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
        raise RuntimeError("model failed")


class _PausedStreamingModel(_ReminderEchoModel):
    def __init__(self) -> None:
        super().__init__()
        self.release = asyncio.Event()

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
        return self._paused_events()

    async def _paused_events(self) -> AsyncIterator[TResponseStreamEvent]:
        async for event in _stream_text_events("unused", self.model):
            yield event
            await self.release.wait()


class _ToolThenAnswerModel(_ReminderEchoModel):
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
            items = input if isinstance(input, list) else []
            self.inputs.append(copy.deepcopy(items))
            return _build_tool_call_response(tools[0].name, {})
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


class _TwoToolApprovalModel(_ReminderEchoModel):
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
        if self.calls < 2:
            tool_index = self.calls
            self.calls += 1
            items = input if isinstance(input, list) else []
            self.inputs.append(copy.deepcopy(items))
            return _build_tool_call_response(tools[tool_index].name, {})
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


class _HandoffModel(_ReminderEchoModel):
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
        return _build_tool_call_response(handoffs[0].tool_name, {})


@function_tool
async def _local_tool() -> str:
    """Return a deterministic local tool result."""
    return "ok"


def _hosted_call() -> ResponseFunctionWebSearch:
    return ResponseFunctionWebSearch(
        id=f"ws_{uuid.uuid4().hex}",
        action=ActionSearch(query="open follow-ups", type="search"),
        status="completed",
        type="web_search_call",
    )


def _reminder_hooks(agent: Agent) -> SystemReminderHooks:
    assert isinstance(agent.hooks, SystemReminderHooks)
    return agent.hooks


def _run_context(agent: Agent, run_id: str) -> RunContextWrapper[MasterContext]:
    context = MasterContext(
        thread_manager=ThreadManager(),
        agents={agent.name: agent},
        current_agent_name=agent.name,
        _current_agent_run_id=run_id,
    )
    return RunContextWrapper(context)


def _contains(items: list[TResponseInputItem], text: str) -> bool:
    return any(isinstance(item, dict) and text in str(item.get("content", "")) for item in items)


def test_callable_reminders_bypass_conversation_starter_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))

    def customer_reminder(ctx: RunContextWrapper[MasterContext], _agent: Agent) -> str:
        return f"Customer:{ctx.context.user_context['customer']}"

    alice_model = _ReminderEchoModel()
    alice = Agency(
        Agent(
            name="SharedAgent",
            instructions="x",
            model=alice_model,
            system_reminders=customer_reminder,
            conversation_starters=["Hello"],
            cache_conversation_starters=True,
        ),
        user_context={"customer": "Alice"},
    )
    alice_result = asyncio.run(alice.get_response("Hello"))

    bob_model = _ReminderEchoModel()
    bob = Agency(
        Agent(
            name="SharedAgent",
            instructions="x",
            model=bob_model,
            system_reminders=customer_reminder,
            conversation_starters=["Hello"],
            cache_conversation_starters=True,
        ),
        user_context={"customer": "Bob"},
    )
    bob_result = asyncio.run(bob.get_response("Hello"))

    assert alice_model.calls == 1
    assert alice_result.final_output == "Customer:Alice"
    assert bob_model.calls == 1
    assert bob_result.final_output == "Customer:Bob"


@pytest.mark.asyncio
async def test_codex_browser_auth_rewrites_injected_reminder_role() -> None:
    model = _CapturingResponsesModel(base_url=CODEX_BASE_URL)
    agent = Agent(name="A", instructions="x", model=model, system_reminders="Remember this")

    await Agency(agent).get_response("next")

    assert [item["role"] for item in model.inputs[0]] == ["developer", "user"]


@pytest.mark.asyncio
async def test_reminder_state_cleans_up_after_model_failure() -> None:
    agent = Agent(name="A", instructions="x", model=_FailingModel(), system_reminders="Remember this")

    with pytest.raises(AgentsException, match="Runner execution failed"):
        await Agency(agent).get_response("next")

    assert _reminder_hooks(agent)._run_state == {}


@pytest.mark.asyncio
async def test_reminder_state_cleans_up_after_stream_cancellation() -> None:
    model = _PausedStreamingModel()
    agent = Agent(name="A", instructions="x", model=model, system_reminders="Remember this")
    response = Agency(agent).get_response_stream("next")

    await anext(response)
    response.cancel()
    async for _event in response:
        pass

    assert _reminder_hooks(agent)._run_state == {}


@pytest.mark.asyncio
async def test_hosted_tool_overflow_matches_local_tool_counting() -> None:
    hosted_agent = Agent(
        name="Hosted",
        instructions="x",
        system_reminders=[EveryNToolCalls(2, "Checkpoint reminder")],
    )
    local_agent = Agent(
        name="Local",
        instructions="x",
        system_reminders=[EveryNToolCalls(2, "Checkpoint reminder")],
    )
    hosted_hooks = _reminder_hooks(hosted_agent)
    local_hooks = _reminder_hooks(local_agent)
    hosted_context = _run_context(hosted_agent, "hosted-run")
    local_context = _run_context(local_agent, "local-run")

    await hosted_hooks.on_llm_end(
        hosted_context,
        hosted_agent,
        ModelResponse(
            output=[_hosted_call() for _ in range(3)],
            usage=Usage(),
            response_id=f"resp_{uuid.uuid4().hex}",
        ),
    )
    for _ in range(3):
        await local_hooks.on_tool_end(local_context, local_agent, _local_tool, "ok")

    hosted_first: list[TResponseInputItem] = []
    local_first: list[TResponseInputItem] = []
    await hosted_hooks.on_llm_start(hosted_context, hosted_agent, None, hosted_first)
    await local_hooks.on_llm_start(local_context, local_agent, None, local_first)

    await hosted_hooks.on_llm_end(
        hosted_context,
        hosted_agent,
        ModelResponse(
            output=[_hosted_call()],
            usage=Usage(),
            response_id=f"resp_{uuid.uuid4().hex}",
        ),
    )
    await local_hooks.on_tool_end(local_context, local_agent, _local_tool, "ok")

    hosted_second: list[TResponseInputItem] = []
    local_second: list[TResponseInputItem] = []
    await hosted_hooks.on_llm_start(hosted_context, hosted_agent, None, hosted_second)
    await local_hooks.on_llm_start(local_context, local_agent, None, local_second)

    assert (
        [_contains(hosted_first, "Checkpoint reminder"), _contains(hosted_second, "Checkpoint reminder")]
        == [
            _contains(local_first, "Checkpoint reminder"),
            _contains(local_second, "Checkpoint reminder"),
        ]
        == [True, True]
    )


def test_bound_method_reminder_with_lock_has_stable_fingerprint() -> None:
    class ReminderOwner:
        def __init__(self) -> None:
            self.lock = threading.Lock()

        def reminder(self, _ctx: RunContextWrapper[MasterContext], _agent: Agent) -> str:
            return "remember"

        def changed_reminder(self, _ctx: RunContextWrapper[MasterContext], _agent: Agent) -> str:
            return "remember differently"

    owner = ReminderOwner()
    agent = Agent(
        name="T",
        instructions="x",
        system_reminders=owner.reminder,
        conversation_starters=["hi"],
        cache_conversation_starters=True,
    )
    changed_agent = Agent(
        name="T",
        instructions="x",
        system_reminders=owner.changed_reminder,
        conversation_starters=["hi"],
        cache_conversation_starters=True,
    )

    assert compute_starter_cache_fingerprint(agent) != compute_starter_cache_fingerprint(changed_agent)


@pytest.mark.asyncio
async def test_agent_clone_replaces_internal_reminder_hooks() -> None:
    original = Agent(name="Original", instructions="x", system_reminders="old reminder")

    inherited_model = _ReminderEchoModel()
    inherited = original.clone(name="Inherited", model=inherited_model)
    await Agency(inherited).get_response("next")

    disabled_model = _ReminderEchoModel()
    disabled = original.clone(name="Disabled", model=disabled_model, system_reminders=[])
    await Agency(disabled).get_response("next")

    replacement_model = _ReminderEchoModel()
    replacement = original.clone(name="Replacement", model=replacement_model, system_reminders="new reminder")
    await Agency(replacement).get_response("next")

    assert _contains(inherited_model.inputs[0], "old reminder")
    assert not _contains(disabled_model.inputs[0], "old reminder")
    assert _contains(replacement_model.inputs[0], "new reminder")
    assert not _contains(replacement_model.inputs[0], "old reminder")


@pytest.mark.asyncio
async def test_user_message_reminder_survives_concurrent_runs_on_shared_thread() -> None:
    """Two `get_response` calls racing on the same Agency must each keep their own reminder.

    `_has_current_top_level_user_message` scans thread history in reverse looking for the
    user message that started *this* run. When two runs interleave on one thread, the
    newest message can belong to the other run; the scan must skip past it and keep
    looking, not abort early and report the reminder missing.
    """
    model = _ReminderEchoModel()
    agent = Agent(name="Concurrent", instructions="x", model=model, system_reminders="reminder!")
    agency = Agency(agent)

    first_result, second_result = await asyncio.gather(
        agency.get_response("message one"),
        agency.get_response("message two"),
    )

    assert model.calls == 2
    assert _contains(model.inputs[0], "reminder!")
    assert _contains(model.inputs[1], "reminder!")
    assert first_result.final_output == "reminder!"
    assert second_result.final_output == "reminder!"

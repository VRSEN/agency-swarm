from collections.abc import AsyncIterator

import pytest
from agents import Tool
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff as AgentsHandoff
from agents.items import HandoffOutputItem, ModelResponse, TResponseInputItem, TResponseStreamEvent
from agents.lifecycle import RunHooksBase
from agents.model_settings import ModelSettings
from agents.models.interface import Model, ModelTracing
from openai.types.responses.response_prompt_param import ResponsePromptParam

from agency_swarm import Agency, Agent, GuardrailFunctionOutput, RunContextWrapper, input_guardrail, output_guardrail
from agency_swarm.agent.context_types import AgencyContext, AgentRuntimeState
from agency_swarm.agent.conversation_starters_cache import (
    build_run_items_from_cached,
    compute_starter_cache_fingerprint,
    is_simple_text_message,
    load_cached_starter,
)
from agency_swarm.context import MasterContext
from agency_swarm.tools.send_message import Handoff
from agency_swarm.utils.thread import ThreadManager
from tests.deterministic_model import DeterministicModel, _build_message_response, _stream_text_events


@input_guardrail(name="RequireSupportPrefix")
def require_support_prefix(
    context: RunContextWrapper, agent: Agent, input_message: str | list[str]
) -> GuardrailFunctionOutput:
    return GuardrailFunctionOutput(output_info="", tripwire_triggered=False)


@output_guardrail(name="BlockEmails")
def block_emails(context: RunContextWrapper, agent: Agent, response_text: str) -> GuardrailFunctionOutput:
    return GuardrailFunctionOutput(output_info="", tripwire_triggered=False)


class SystemInstructionsEchoModel(Model):
    def __init__(self, model: str = "test-system-instructions") -> None:
        self.model = model

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[AgentsHandoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> ModelResponse:
        text = system_instructions or ""
        return _build_message_response(text, self.model)

    def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[AgentsHandoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        text = system_instructions or ""
        return _stream_text_events(text, self.model)


class RecordingHooks(RunHooksBase[MasterContext, Agent]):
    def __init__(self) -> None:
        self.agent_started = 0

    async def on_agent_start(self, context: RunContextWrapper[MasterContext], agent: Agent) -> None:
        self.agent_started += 1


def _build_minimal_context(agent: Agent, shared_instructions: str | None) -> AgencyContext:
    return AgencyContext(
        agency_instance=None,
        thread_manager=ThreadManager(),
        runtime_state=AgentRuntimeState(agent.tool_concurrency_manager),
        shared_instructions=shared_instructions,
    )


@pytest.mark.asyncio
async def test_starter_cache_respects_shared_instructions(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))
    starter = "Hello starter"
    agent = Agent(
        name="CacheAgent",
        instructions="Base instructions.",
        model=SystemInstructionsEchoModel(),
        conversation_starters=[starter],
        cache_conversation_starters=True,
    )

    context_a = _build_minimal_context(agent, "Shared A")
    result_a = await agent.get_response(starter, agency_context=context_a)
    assert isinstance(result_a.final_output, str)
    assert "Shared A" in result_a.final_output

    context_b = _build_minimal_context(agent, "Shared B")
    result_b = await agent.get_response(starter, agency_context=context_b)
    assert isinstance(result_b.final_output, str)
    assert "Shared B" in result_b.final_output


@pytest.mark.asyncio
async def test_starter_cache_reload_keeps_shared_instructions(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))
    starter = "Hello starter"
    shared = "Shared instructions"
    agent = Agent(
        name="CacheAgent",
        instructions="Base instructions.",
        model=SystemInstructionsEchoModel(),
        conversation_starters=[starter],
        cache_conversation_starters=True,
    )

    context = _build_minimal_context(agent, shared)
    await agent.get_response(starter, agency_context=context)

    reloaded = Agent(
        name="CacheAgent",
        instructions="Base instructions.",
        model=SystemInstructionsEchoModel(),
        conversation_starters=[starter],
        cache_conversation_starters=True,
    )
    reloaded.refresh_conversation_starters_cache(shared_instructions=shared)

    cached = load_cached_starter(
        reloaded.name,
        starter,
        expected_fingerprint=reloaded._conversation_starters_fingerprint,
    )

    assert cached is not None


@pytest.mark.asyncio
async def test_starter_cache_skips_hooks_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))
    starter = "Hello starter"
    agent = Agent(
        name="CacheAgent",
        instructions="Base instructions.",
        model=SystemInstructionsEchoModel(),
        conversation_starters=[starter],
        cache_conversation_starters=True,
    )

    first_context = _build_minimal_context(agent, None)
    await agent.get_response(starter, agency_context=first_context)

    hooks = RecordingHooks()
    second_context = _build_minimal_context(agent, None)
    await agent.get_response(starter, agency_context=second_context, hooks_override=hooks)

    assert hooks.agent_started >= 1


def test_is_simple_text_message_requires_single_user_item() -> None:
    items = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello there."},
    ]

    assert is_simple_text_message(items) is False


def test_is_simple_text_message_rejects_multiple_user_items() -> None:
    items = [
        {"role": "user", "content": "Hello."},
        {"role": "user", "content": "Follow-up."},
    ]

    assert is_simple_text_message(items) is False


@pytest.mark.asyncio
async def test_warm_conversation_starters_cache_uses_runtime_tools(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))
    starter = "Send a message to Worker: hello"
    sender = Agent(
        name="Sender",
        instructions="Send messages to Worker when asked.",
        model=DeterministicModel(default_response="NO_TOOL"),
        conversation_starters=[starter],
        cache_conversation_starters=False,
    )
    worker = Agent(
        name="Worker",
        instructions="A helpful worker.",
        model=DeterministicModel(default_response="OK"),
    )
    agency = Agency(sender, communication_flows=[(sender, worker)])

    sender.cache_conversation_starters = True
    sender.refresh_conversation_starters_cache(runtime_state=agency.get_agent_runtime_state(sender.name))
    await sender.warm_conversation_starters_cache(agency.get_agent_context(sender.name))

    cached = load_cached_starter(
        sender.name,
        starter,
        expected_fingerprint=sender._conversation_starters_fingerprint,
    )

    assert cached is not None
    assert any(
        isinstance(item, dict) and item.get("type") == "function_call" and item.get("name") == "send_message"
        for item in cached.items
    )


def test_starter_cache_fingerprint_includes_guardrails() -> None:
    agent_with_guardrails = Agent(
        name="GuardrailAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
        input_guardrails=[require_support_prefix],
        output_guardrails=[block_emails],
    )
    agent_without_guardrails = Agent(
        name="BaselineAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
        input_guardrails=[],
        output_guardrails=[],
    )

    fingerprint_with = compute_starter_cache_fingerprint(agent_with_guardrails)
    fingerprint_without = compute_starter_cache_fingerprint(agent_without_guardrails)

    assert fingerprint_with != fingerprint_without


def test_starter_cache_fingerprint_includes_runtime_send_message_tools() -> None:
    sender = Agent(
        name="SenderAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
    )
    recipient = Agent(
        name="RecipientAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
    )
    runtime_state = AgentRuntimeState()

    fingerprint_before = compute_starter_cache_fingerprint(sender, runtime_state=runtime_state)
    sender.register_subagent(recipient, runtime_state=runtime_state)
    fingerprint_after = compute_starter_cache_fingerprint(sender, runtime_state=runtime_state)

    assert fingerprint_before != fingerprint_after


def test_starter_cache_fingerprint_includes_runtime_handoffs() -> None:
    sender = Agent(
        name="HandoffSender",
        instructions="You are helpful.",
        model="gpt-5-mini",
    )
    recipient = Agent(
        name="HandoffRecipient",
        instructions="You are helpful.",
        model="gpt-5-mini",
    )
    runtime_state = AgentRuntimeState()

    fingerprint_before = compute_starter_cache_fingerprint(sender, runtime_state=runtime_state)
    runtime_state.handoffs.append(Handoff().create_handoff(recipient))
    fingerprint_after = compute_starter_cache_fingerprint(sender, runtime_state=runtime_state)

    assert fingerprint_before != fingerprint_after


def test_cached_handoff_output_preserves_type() -> None:
    agent = Agent(
        name="CacheAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
    )
    items = [
        {
            "type": "handoff_output_item",
            "call_id": "call_handoff_1",
            "output": '{"assistant": "Worker"}',
        }
    ]

    run_items = build_run_items_from_cached(agent, items)

    assert len(run_items) == 1
    assert isinstance(run_items[0], HandoffOutputItem)

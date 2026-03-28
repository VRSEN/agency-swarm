import asyncio
import dataclasses
import inspect
import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents import Tool
from agents.agent_output import AgentOutputSchema, AgentOutputSchemaBase
from agents.handoffs import Handoff as SDKHandoff
from agents.items import HandoffOutputItem, ModelResponse, TResponseInputItem, TResponseStreamEvent
from agents.lifecycle import RunHooksBase
from agents.model_settings import ModelSettings
from agents.models.interface import Model, ModelTracing
from agents.models.openai_responses import OpenAIResponsesModel
from agents.tool import (
    ApplyPatchTool,
    CodeInterpreterTool,
    ComputerTool,
    FileSearchTool,
    FunctionTool,
    HostedMCPTool,
    ImageGenerationTool,
    LocalShellTool,
    ShellTool,
    WebSearchTool,
)
from openai import AsyncOpenAI
from openai.types.responses.response_prompt_param import ResponsePromptParam
from pydantic import BaseModel

from agency_swarm import Agency, Agent, GuardrailFunctionOutput, RunContextWrapper, input_guardrail, output_guardrail
from agency_swarm.agent.context_types import AgencyContext, AgentRuntimeState
from agency_swarm.agent.conversation_starters_cache import (
    build_run_items_from_cached,
    compute_starter_cache_fingerprint,
    extract_final_output_text,
    extract_starter_segment,
    extract_text_from_content,
    extract_user_text,
    is_simple_text_message,
    load_cached_starter,
    load_cached_starters,
    match_conversation_starter,
    merge_cacheable_starters,
    parse_cached_output,
    prepare_cached_items_for_replay,
    reorder_cached_items_for_tools,
    save_cached_starter,
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
        handoffs: list[SDKHandoff],
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
        handoffs: list[SDKHandoff],
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
async def test_quick_replies_are_cached_without_conversation_starters(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))
    quick_reply = "hi"
    agent = Agent(
        name="CacheAgent",
        instructions="Base instructions.",
        model=SystemInstructionsEchoModel(),
        quick_replies=[quick_reply],
        cache_conversation_starters=True,
    )

    context = _build_minimal_context(agent, None)
    await agent.get_response(quick_reply, agency_context=context)

    cached = load_cached_starter(
        agent.name,
        quick_reply,
        expected_fingerprint=agent._conversation_starters_fingerprint,
    )
    assert cached is not None


@pytest.mark.asyncio
async def test_quick_replies_cache_and_replay_when_starter_cache_flag_is_disabled(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))
    quick_reply = "hi"
    model = SystemInstructionsEchoModel()
    agent = Agent(
        name="CacheAgent",
        instructions="Base instructions.",
        model=model,
        quick_replies=[quick_reply],
        cache_conversation_starters=False,
    )

    first_context = _build_minimal_context(agent, None)
    first_result = await agent.get_response(quick_reply, agency_context=first_context)
    assert isinstance(first_result.final_output, str)

    cached = load_cached_starter(agent.name, quick_reply)
    assert cached is not None
    expected_output = extract_final_output_text(cached.items)
    assert expected_output

    async def _fail_get_response(*_args, **_kwargs):
        raise RuntimeError("model should not be called for cached quick reply")

    monkeypatch.setattr(model, "get_response", _fail_get_response)

    second_context = _build_minimal_context(agent, None)
    replay_result = await agent.get_response(quick_reply, agency_context=second_context)
    assert replay_result.final_output == expected_output


@pytest.mark.asyncio
@patch("agency_swarm.agent.execution_helpers.Runner.run", new_callable=AsyncMock)
async def test_quick_reply_cache_is_skipped_for_openai_previous_response_id(
    mock_runner_run,
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))
    quick_reply = "hi"
    agent = Agent(
        name="CacheAgent",
        instructions="Base instructions.",
        model="gpt-5.4-mini",
        quick_replies=[quick_reply],
        cache_conversation_starters=False,
    )

    save_cached_starter(
        agent.name,
        quick_reply,
        [{"type": "message", "role": "assistant", "content": "CACHED"}],
    )
    mock_runner_run.return_value = MagicMock(new_items=[], final_output="LIVE")

    context = _build_minimal_context(agent, None)
    result = await agent.get_response(quick_reply, agency_context=context, previous_response_id="resp_1")

    assert result.final_output == "LIVE"
    assert mock_runner_run.await_count == 1


@pytest.mark.asyncio
async def test_quick_replies_stream_replay_when_starter_cache_flag_is_disabled(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))
    quick_reply = "hi"
    model = SystemInstructionsEchoModel()
    agent = Agent(
        name="CacheAgent",
        instructions="Base instructions.",
        model=model,
        quick_replies=[quick_reply],
        cache_conversation_starters=False,
    )

    first_context = _build_minimal_context(agent, None)
    await agent.get_response(quick_reply, agency_context=first_context)
    cached = load_cached_starter(agent.name, quick_reply)
    assert cached is not None
    expected_output = extract_final_output_text(cached.items)
    assert expected_output

    def _fail_stream_response(*_args, **_kwargs):
        raise RuntimeError("model stream should not be called for cached quick reply")

    monkeypatch.setattr(model, "stream_response", _fail_stream_response)

    stream_context = _build_minimal_context(agent, None)
    stream = agent.get_response_stream(quick_reply, agency_context=stream_context)
    async for _event in stream:
        pass
    assert stream.final_output == expected_output


@pytest.mark.asyncio
async def test_conversation_starter_not_cached_when_starter_cache_flag_is_disabled(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))
    starter = "Hello starter"
    agent = Agent(
        name="CacheAgent",
        instructions="Base instructions.",
        model=SystemInstructionsEchoModel(),
        conversation_starters=[starter],
        cache_conversation_starters=False,
    )

    context = _build_minimal_context(agent, None)
    await agent.get_response(starter, agency_context=context)

    cached = load_cached_starter(agent.name, starter)
    assert cached is None


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


def test_is_simple_text_message_rejects_invalid_user_item_shapes() -> None:
    invalid_cases = [
        [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello there."},
        ],
        [
            {"role": "user", "content": "Hello."},
            {"role": "user", "content": "Follow-up."},
        ],
    ]

    for items in invalid_cases:
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


def test_starter_cache_fingerprint_changes_for_guardrails_runtime_tools_and_handoffs() -> None:
    agent_with_guardrails = Agent(
        name="GuardrailAgent",
        instructions="You are helpful.",
        model="gpt-5.4-mini",
        input_guardrails=[require_support_prefix],
        output_guardrails=[block_emails],
    )
    agent_without_guardrails = Agent(
        name="BaselineAgent",
        instructions="You are helpful.",
        model="gpt-5.4-mini",
        input_guardrails=[],
        output_guardrails=[],
    )
    assert compute_starter_cache_fingerprint(agent_with_guardrails) != compute_starter_cache_fingerprint(
        agent_without_guardrails
    )

    sender = Agent(
        name="SenderAgent",
        instructions="You are helpful.",
        model="gpt-5.4-mini",
    )
    recipient = Agent(
        name="RecipientAgent",
        instructions="You are helpful.",
        model="gpt-5.4-mini",
    )
    runtime_state = AgentRuntimeState()
    fingerprint_before = compute_starter_cache_fingerprint(sender, runtime_state=runtime_state)
    sender.register_subagent(recipient, runtime_state=runtime_state)
    fingerprint_after = compute_starter_cache_fingerprint(sender, runtime_state=runtime_state)
    assert fingerprint_before != fingerprint_after

    handoff_sender = Agent(
        name="HandoffSender",
        instructions="You are helpful.",
        model="gpt-5.4-mini",
    )
    handoff_recipient = Agent(
        name="HandoffRecipient",
        instructions="You are helpful.",
        model="gpt-5.4-mini",
    )
    handoff_runtime = AgentRuntimeState()
    handoff_before = compute_starter_cache_fingerprint(handoff_sender, runtime_state=handoff_runtime)
    handoff_runtime.handoffs.append(Handoff().create_handoff(handoff_recipient))
    handoff_after = compute_starter_cache_fingerprint(handoff_sender, runtime_state=handoff_runtime)
    assert handoff_before != handoff_after


class _StructuredOutput(BaseModel):
    answer: str


def test_cache_helper_text_matching_and_reordering_utilities() -> None:
    merged = merge_cacheable_starters(
        conversation_starters=["Hi", "  hi  ", "", "Hello"],
        quick_replies=["HI", "hello", "Yo"],
    )
    assert merged == ["Hi", "Hello", "Yo"]

    assert extract_text_from_content("hello") == "hello"
    assert extract_text_from_content([{"text": "Hello"}, {"text": " world"}]) == "Hello world"
    assert extract_text_from_content([{"type": "input_text"}, 123]) is None

    extract_items: list[TResponseInputItem] = [
        "skip-me",
        {"role": "assistant", "content": "Not user"},
        {"role": "user", "content": [{"type": "input_text", "text": "Final user text"}]},
    ]
    assert extract_user_text(extract_items) == "Final user text"

    match_items: list[TResponseInputItem] = [
        {"role": "user", "content": "Hi there"},
        {"role": "assistant", "type": "message", "content": "Hello"},
    ]
    segment_items: list[TResponseInputItem] = [
        {"role": "user", "content": "Hi there"},
        {"role": "assistant", "type": "message", "content": "Hello"},
        {"role": "user", "callerAgent": "Worker", "content": "Nested user"},
        {"role": "assistant", "type": "message", "content": "Nested reply"},
        {"role": "user", "content": "Second question"},
    ]

    assert match_conversation_starter(match_items, None) is None
    assert match_conversation_starter(match_items, ["unknown"]) is None
    assert match_conversation_starter(match_items, ["HI THERE"]) == "HI THERE"

    segment = extract_starter_segment(segment_items, "hi there")
    assert segment is not None
    assert segment[0]["content"] == "Hi there"
    assert segment[-1]["content"] == "Nested reply"
    assert extract_starter_segment(segment_items, "missing") is None
    assert extract_starter_segment(segment_items, "   ") is None

    call_item = {"type": "function_call", "agent": "Primary", "call_id": "call_1", "agent_run_id": "run_1"}
    child_item = {"type": "message", "agent": "Worker", "parent_run_id": "call_1"}
    unrelated = {"type": "message", "agent": "Primary", "role": "assistant"}
    reordered = reorder_cached_items_for_tools([child_item, call_item, unrelated], "Primary")
    assert reordered[0] is call_item
    assert reordered[1] is child_item
    assert reordered[2] is unrelated
    assert reorder_cached_items_for_tools([], "Primary") == []


def test_cache_serialization_and_replay_utilities(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))
    starter = "Hello starter"
    starter_items = [{"type": "message", "role": "assistant", "content": "cached"}]
    saved = save_cached_starter("CacheAgent", starter, starter_items, metadata={"fingerprint": "fp"})
    cache_file = next((tmp_path / "starter_cache").glob("*.json"))

    assert load_cached_starter("CacheAgent", starter, expected_fingerprint="fp") == saved
    assert load_cached_starter("CacheAgent", starter, expected_fingerprint="mismatch") is None

    cache_file.write_text("{", encoding="utf-8")
    assert load_cached_starter("CacheAgent", starter) is None

    cache_file.write_text(json.dumps(["not", "dict"]), encoding="utf-8")
    assert load_cached_starter("CacheAgent", starter) is None

    cache_file.write_text(json.dumps({"items": "bad"}), encoding="utf-8")
    assert load_cached_starter("CacheAgent", starter) is None

    cache_file.write_text(
        json.dumps({"prompt": 1, "items": starter_items, "metadata": {"source": "chat_history"}}),
        encoding="utf-8",
    )
    assert load_cached_starter("CacheAgent", starter) is None

    save_cached_starter("CacheAgent", "hello", starter_items)
    loaded = load_cached_starters("CacheAgent", [" ", "", "hello"])
    assert list(loaded.keys()) == ["hello"]

    replay_source: list[TResponseInputItem] = [
        "skip",
        {"type": "message", "role": "assistant", "content": "hello"},
        {"type": "function_call", "role": "assistant", "agent": "AgentA", "call_id": "old_call", "id": "fc_old"},
        {"type": "function_call_output", "call_id": "old_call", "output": "done", "id": "out_old"},
        {"type": "function_call", "role": "assistant", "call_id": 123},
        {"type": "function_call_output", "call_id": 123, "output": "fallback"},
    ]
    replayed = prepare_cached_items_for_replay(replay_source, run_trace_id="trace_1", parent_run_id="parent_1")
    assert len(replayed) == 5
    assert all(item["run_trace_id"] == "trace_1" for item in replayed)
    assert all(item["parent_run_id"] == "parent_1" for item in replayed)
    assert replayed[0]["id"].startswith("msg_")
    assert replayed[1]["id"].startswith("fc_")
    assert replayed[1]["call_id"] == replayed[2]["call_id"]
    assert "id" not in replayed[2]
    assert replayed[3]["call_id"] == replayed[4]["call_id"]
    assert replayed[3]["call_id"].startswith("call_")

    without_parent = prepare_cached_items_for_replay(replay_source, run_trace_id="trace_2", parent_run_id=None)
    assert all("parent_run_id" not in item for item in without_parent)

    assert parse_cached_output("plain", None) == "plain"
    assert parse_cached_output("plain", str) == "plain"
    assert parse_cached_output("plain", AgentOutputSchema(str)) == "plain"
    parsed = parse_cached_output('{"answer":"yes"}', _StructuredOutput)
    assert isinstance(parsed, _StructuredOutput)
    assert parsed.answer == "yes"
    parsed_schema = parse_cached_output('{"answer":"yes"}', AgentOutputSchema(_StructuredOutput))
    assert isinstance(parsed_schema, _StructuredOutput)
    assert parsed_schema.answer == "yes"

    build_agent = Agent(name="BuildAgent", instructions="Test", model="gpt-5.4-mini")
    build_items: list[TResponseInputItem] = [
        "skip",
        {"type": "message", "role": "assistant", "content": "Assistant reply"},
        {"type": "function_call", "agent": "BuildAgent", "call_id": "call_1", "name": "do_work", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call_1", "output": "done"},
        {"type": "reasoning", "id": "bad", "summary": "invalid"},
    ]
    run_items = build_run_items_from_cached(build_agent, build_items)
    assert len(run_items) == 3
    assert run_items[0].type == "message_output_item"
    assert run_items[1].type == "tool_call_item"
    assert run_items[2].type == "tool_call_output_item"

    handoff_items = [{"type": "handoff_output_item", "call_id": "call_handoff_1", "output": '{"assistant": "Worker"}'}]
    handoff_run_items = build_run_items_from_cached(build_agent, handoff_items)
    assert len(handoff_run_items) == 1
    assert isinstance(handoff_run_items[0], HandoffOutputItem)


def _make_fingerprint_agent(*, tools: list[object], mcp_config: object, output_type: object = None) -> object:
    return SimpleNamespace(
        instructions="Base instructions",
        prompt=None,
        model="gpt-5.4-mini",
        model_settings=None,
        input_guardrails=[],
        output_guardrails=[],
        tools=tools,
        tool_use_behavior="run_llm_again",
        reset_tool_choice=True,
        mcp_servers=[],
        mcp_config=mcp_config,
        handoffs=[],
        output_type=output_type,
    )


def test_compute_starter_cache_fingerprint_utilities(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = FunctionTool(
        name="echo",
        description="echo",
        params_json_schema={"type": "object", "properties": {"message": {"type": "string"}}},
        on_invoke_tool=lambda _wrapper, _json: asyncio.sleep(0, result="ok"),
        strict_json_schema=True,
    )
    first = _make_fingerprint_agent(
        tools=[tool],
        mcp_config={"api_key": "secret-one", "authorization": "Bearer A", "safe": "same"},
    )
    second = _make_fingerprint_agent(
        tools=[tool],
        mcp_config={"api_key": "secret-two", "authorization": "Bearer B", "safe": "same"},
    )

    assert compute_starter_cache_fingerprint(first) == compute_starter_cache_fingerprint(second)

    agent_a = _make_fingerprint_agent(tools=[], mcp_config={"region": "eu"})
    agent_b = _make_fingerprint_agent(tools=[], mcp_config={"region": "us"})
    assert compute_starter_cache_fingerprint(agent_a) != compute_starter_cache_fingerprint(agent_b)

    @dataclasses.dataclass
    class _Config:
        retries: int
        secret_token: str

    class _CallableWithoutQualname:
        __name__ = "callable_no_qualname"

        def __call__(self) -> str:
            return "ok"

    def raising_getsource(_value: object) -> str:
        raise OSError("source unavailable")

    callable_instructions = _CallableWithoutQualname()
    agent = _make_fingerprint_agent(
        tools=[],
        mcp_config=_Config(retries=3, secret_token="token"),
        output_type=AgentOutputSchema(_StructuredOutput),
    )

    with monkeypatch.context() as ctx:
        ctx.setattr(inspect, "getsource", raising_getsource)
        fingerprint = compute_starter_cache_fingerprint(
            agent,
            instructions_override=callable_instructions,
            use_instructions_override=True,
            shared_instructions=123,
        )
    assert isinstance(fingerprint, str)
    assert len(fingerprint) == 64

    class _DummyExecutor:
        __name__ = "dummy_executor"

        async def __call__(self, *args: object, **kwargs: object) -> dict[str, object]:
            return {"stdout": "", "stderr": "", "exit_code": 0}

    class _DummyEditor:
        async def apply(self, patch: str) -> str:  # noqa: ARG002
            return "ok"

    async def _invoke(_wrapper: object, _arguments_json: str) -> str:
        return "ok"

    tools = [
        FunctionTool(
            name="fn_tool",
            description="function tool",
            params_json_schema={"type": "object", "properties": {"value": {"type": "string"}}},
            on_invoke_tool=_invoke,
            strict_json_schema=True,
        ),
        FileSearchTool(vector_store_ids=["vs_1"]),
        WebSearchTool(),
        HostedMCPTool(
            tool_config={
                "type": "mcp",
                "server_label": "srv",
                "server_url": "https://example.com",
                "allowed_tools": ["search"],
                "authorization": "secret-token",
            }
        ),
        CodeInterpreterTool(tool_config={"type": "code_interpreter"}),
        ImageGenerationTool(tool_config={"type": "image_generation"}),
        ComputerTool(computer={"environment": "browser"}),
        ShellTool(executor=_DummyExecutor()),
        LocalShellTool(executor=_DummyExecutor()),
        ApplyPatchTool(editor=_DummyEditor()),
        object(),
    ]

    fingerprints = [
        compute_starter_cache_fingerprint(_make_fingerprint_agent(tools=[tool], mcp_config={})) for tool in tools
    ]

    assert all(isinstance(fingerprint, str) and len(fingerprint) == 64 for fingerprint in fingerprints)


def test_compute_starter_cache_fingerprint_changes_when_openclaw_upstream_provider_changes() -> None:
    agent = _make_fingerprint_agent(tools=[], mcp_config={})

    openai_model = OpenAIResponsesModel(
        model="openclaw:main",
        openai_client=AsyncOpenAI(base_url="http://127.0.0.1:8000/openclaw/v1", api_key="test-key"),
    )
    anthropic_model = OpenAIResponsesModel(
        model="openclaw:main",
        openai_client=AsyncOpenAI(base_url="http://127.0.0.1:8000/openclaw/v1", api_key="test-key"),
    )
    openai_model._agency_swarm_usage_model_name = "openai/gpt-5.4-mini"
    anthropic_model._agency_swarm_usage_model_name = "anthropic/claude-sonnet-4-5"

    agent.model = openai_model
    openai_fingerprint = compute_starter_cache_fingerprint(agent)

    agent.model = anthropic_model
    anthropic_fingerprint = compute_starter_cache_fingerprint(agent)

    assert openai_fingerprint != anthropic_fingerprint

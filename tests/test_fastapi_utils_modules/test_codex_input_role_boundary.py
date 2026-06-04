import asyncio
import inspect
from collections.abc import AsyncGenerator
from typing import Any, cast

import pytest
from agents import ModelSettings, RunConfig, Tool
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff as SDKHandoff
from agents.items import ModelResponse, TResponseInputItem
from agents.models.interface import Model, ModelProvider
from agents.models.multi_provider import MultiProvider, MultiProviderMap
from agents.models.openai_provider import OpenAIProvider
from agents.models.openai_responses import OpenAIResponsesModel
from agents.run_config import CallModelData, ModelInputData
from openai import AsyncOpenAI
from openai.types.responses.response_prompt_param import ResponsePromptParam

from agency_swarm import Agency, AgencyContext, Agent
from agency_swarm.agent.codex_model_input import with_codex_model_input_role_rewrite
from agency_swarm.integrations.fastapi_utils.endpoint_handlers import (
    ActiveRunRegistry,
    make_agui_chat_endpoint,
    make_response_endpoint,
    make_stream_endpoint,
)
from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig, RunAgentInputCustom
from agency_swarm.messages import MessageFormatter
from agency_swarm.tools import Handoff
from agency_swarm.utils.thread import ThreadManager
from tests.deterministic_model import DeterministicModel, _build_message_response

CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
OPENAI_BASE_URL = "https://api.openai.com/v1"


class _HttpRequest:
    async def is_disconnected(self) -> bool:
        return False


class _RunResult:
    new_items: list[Any] = []
    final_output = "ok"


class _StreamedResult:
    final_output = "ok"
    new_items: list[Any] = []

    def stream_events(self) -> AsyncGenerator[dict[str, str]]:
        return _empty_stream()

    def cancel(self, *_args: Any, **_kwargs: Any) -> None:
        return None


async def _empty_stream() -> AsyncGenerator[dict[str, str]]:
    if False:
        yield {}


class _NonOpenAIProvider(ModelProvider):
    def get_model(self, model_name: str | None) -> Model:
        raise AssertionError(f"unexpected model lookup for {model_name}")


class _CapturingResponsesModel(OpenAIResponsesModel):
    def __init__(self, *, base_url: str) -> None:
        super().__init__(
            model="gpt-5.4-mini",
            openai_client=AsyncOpenAI(api_key="sk-test", base_url=base_url),
        )
        self.inputs: list[list[dict[str, Any]]] = []

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[SDKHandoff],
        tracing,
        previous_response_id: str | None = None,
        conversation_id: str | None = None,
        prompt: ResponsePromptParam | None = None,
    ) -> ModelResponse:
        if isinstance(input, list):
            self.inputs.append(cast(list[dict[str, Any]], input))
        return _build_message_response("worker done", str(self.model))


async def _attach_noop(_agency: Agency) -> None:
    return None


def _history() -> list[dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": "web results",
            "message_origin": "web_search_preservation",
            "agent": "A",
            "callerAgent": None,
            "timestamp": 1,
        },
        {
            "role": "system",
            "content": "file results",
            "message_origin": "file_search_preservation",
            "agent": "A",
            "callerAgent": None,
            "timestamp": 2,
        },
        {
            "role": "system",
            "content": "non-preservation replay",
            "message_origin": "other_replay",
            "agent": "A",
            "callerAgent": None,
            "timestamp": 3,
        },
    ]


def _roles(messages: list[dict[str, Any]]) -> list[str]:
    return [message["role"] for message in messages]


def _agency_factory(**kwargs: Any) -> Agency:
    return Agency(
        Agent(name="A", instructions="normal agent instructions"), load_threads_callback=kwargs["load_threads_callback"]
    )


async def _filtered_roles(
    run_config: RunConfig,
    agent: Agent,
    messages: list[dict[str, Any]],
) -> list[str]:
    model_data = ModelInputData(input=cast(list[TResponseInputItem], messages), instructions=None)
    filter_func = run_config.call_model_input_filter
    assert filter_func is not None
    filtered = await filter_func(CallModelData(model_data=model_data, agent=agent, context=None))
    return _roles(cast(list[dict[str, Any]], filtered.input))


def _model_call_roles(agent: Agent, run_config: RunConfig | None) -> list[str]:
    replayed = _history()
    thread_manager = ThreadManager()
    thread_manager._store.messages = replayed
    context = AgencyContext(agency_instance=None, thread_manager=thread_manager)

    history = cast(
        list[dict[str, Any]],
        MessageFormatter.prepare_history_for_runner(
            [{"role": "user", "content": "next"}],
            agent,
            None,
            context,
            run_config_override=run_config,
        ),
    )

    assert _roles(replayed[:3]) == ["system", "system", "system"]
    assert _roles(history) == ["system", "system", "system", "user"]
    wrapped = with_codex_model_input_role_rewrite(run_config or RunConfig())
    return asyncio.run(_filtered_roles(wrapped, agent, history))


def _multi_provider_unknown_prefix_model_id(base_url: str) -> MultiProvider:
    if "unknown_prefix_mode" not in inspect.signature(MultiProvider).parameters:
        pytest.skip("MultiProvider unknown_prefix_mode is not available in this Agents SDK")
    kwargs = {"openai_api_key": "sk-test", "openai_base_url": base_url}
    kwargs["unknown_prefix_mode"] = "model_id"
    provider = MultiProvider(**kwargs)
    routed, resolved = provider._resolve_prefixed_model(
        original_model_name="anthropic/foo",
        prefix="anthropic",
        stripped_model_name="foo",
    )
    assert routed is provider.openai_provider
    assert resolved == "anthropic/foo"
    return provider


def test_model_call_rewrites_system_replay_for_codex_openai_provider_run_config() -> None:
    agent = Agent(name="A", instructions="normal agent instructions", model="gpt-5.4-mini")
    run_config = RunConfig(
        model_provider=OpenAIProvider(api_key="sk-test", base_url=CODEX_BASE_URL),
    )

    assert _model_call_roles(agent, run_config) == ["developer", "developer", "developer", "user"]


def test_model_call_rewrites_system_replay_for_codex_openai_provider_default_model() -> None:
    agent = Agent(name="A", instructions="normal agent instructions", model=None)
    run_config = RunConfig(
        model_provider=OpenAIProvider(api_key="sk-test", base_url=CODEX_BASE_URL),
    )

    assert _model_call_roles(agent, run_config) == ["developer", "developer", "developer", "user"]


def test_model_call_keeps_system_replay_for_codex_openai_provider_base_url_with_non_codex_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agency_swarm.messages import codex_input

    agent = Agent(name="A", instructions="normal agent instructions", model="gpt-5.4-mini")
    run_config = RunConfig(
        model_provider=OpenAIProvider(api_key="sk-test", base_url=CODEX_BASE_URL),
    )
    monkeypatch.setattr(
        codex_input, "get_default_openai_client", lambda: AsyncOpenAI(api_key="sk-test", base_url=OPENAI_BASE_URL)
    )

    assert _model_call_roles(agent, run_config) == ["system", "system", "system", "user"]


def test_model_call_rewrites_system_replay_for_codex_openai_provider_custom_model_name() -> None:
    agent = Agent(name="A", instructions="normal agent instructions", model="anthropic/foo")
    run_config = RunConfig(
        model_provider=OpenAIProvider(api_key="sk-test", base_url=CODEX_BASE_URL),
    )

    assert _model_call_roles(agent, run_config) == ["developer", "developer", "developer", "user"]


def test_model_call_rewrites_system_replay_for_lazy_openai_provider_codex_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agency_swarm.messages import codex_input

    agent = Agent(name="A", instructions="normal agent instructions", model="gpt-5.4-mini")
    run_config = RunConfig(
        model_provider=OpenAIProvider(api_key="sk-test"),
    )
    monkeypatch.setattr(codex_input, "get_default_openai_client", lambda: None)
    monkeypatch.setenv("OPENAI_BASE_URL", CODEX_BASE_URL)

    assert _model_call_roles(agent, run_config) == ["developer", "developer", "developer", "user"]


def test_model_call_rewrites_system_replay_for_default_provider_codex_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agency_swarm.messages import codex_input

    agent = Agent(name="A", instructions="normal agent instructions", model="gpt-5.4-mini")
    monkeypatch.setattr(codex_input, "get_default_openai_client", lambda: None)
    monkeypatch.setenv("OPENAI_BASE_URL", CODEX_BASE_URL)

    assert _model_call_roles(agent, None) == ["developer", "developer", "developer", "user"]


def test_model_call_rewrites_system_replay_for_codex_multi_provider_base_url() -> None:
    agent = Agent(name="A", instructions="normal agent instructions", model="gpt-5.4-mini")
    run_config = RunConfig(
        model_provider=MultiProvider(openai_api_key="sk-test", openai_base_url=CODEX_BASE_URL),
    )

    assert _model_call_roles(agent, run_config) == ["developer", "developer", "developer", "user"]


@pytest.mark.parametrize(
    ("base_url", "expected_roles"),
    [
        (CODEX_BASE_URL, ["developer", "developer", "developer", "user"]),
        (OPENAI_BASE_URL, ["system", "system", "system", "user"]),
    ],
)
def test_model_call_rewrites_system_replay_for_litellm_model_base_url(
    base_url: str,
    expected_roles: list[str],
) -> None:
    pytest.importorskip("agents.extensions.models.litellm_model", exc_type=ImportError)

    from agents.extensions.models.litellm_model import LitellmModel

    agent = Agent(
        name="A",
        instructions="normal agent instructions",
        model=LitellmModel(model="openai/gpt-5.4-mini", base_url=base_url, api_key="sk-test"),
    )

    assert _model_call_roles(agent, None) == expected_roles


@pytest.mark.parametrize(
    ("model", "expected_roles"),
    [
        ("openai/gpt-5.4-mini", ["developer", "developer", "developer", "user"]),
        ("litellm/openai/gpt-5.4-mini", ["system", "system", "system", "user"]),
        ("any-llm/openrouter/gpt-5.4-mini", ["system", "system", "system", "user"]),
    ],
)
def test_model_call_preserves_multi_provider_builtin_prefix_boundaries(
    model: str,
    expected_roles: list[str],
) -> None:
    agent = Agent(name="A", instructions="normal agent instructions", model=model)
    run_config = RunConfig(
        model_provider=MultiProvider(openai_api_key="sk-test", openai_base_url=CODEX_BASE_URL),
    )

    assert _model_call_roles(agent, run_config) == expected_roles


def test_model_call_rewrites_system_replay_for_nested_codex_multi_provider_route() -> None:
    nested = MultiProvider(openai_api_key="sk-test", openai_base_url=CODEX_BASE_URL)
    provider_map = MultiProviderMap()
    provider_map.add_provider("tenant", nested)
    provider = MultiProvider(provider_map=provider_map)
    routed, resolved = provider._resolve_prefixed_model(
        original_model_name="tenant/gpt-5.4-mini",
        prefix="tenant",
        stripped_model_name="gpt-5.4-mini",
    )
    assert routed is nested
    assert resolved == "gpt-5.4-mini"

    agent = Agent(name="A", instructions="normal agent instructions", model="tenant/gpt-5.4-mini")
    run_config = RunConfig(model_provider=provider)

    assert _model_call_roles(agent, run_config) == ["developer", "developer", "developer", "user"]


def test_model_call_rewrites_system_replay_for_codex_multi_provider_client() -> None:
    agent = Agent(name="A", instructions="normal agent instructions", model="gpt-5.4-mini")
    run_config = RunConfig(
        model_provider=MultiProvider(openai_client=AsyncOpenAI(api_key="sk-test", base_url=CODEX_BASE_URL)),
    )

    assert _model_call_roles(agent, run_config) == ["developer", "developer", "developer", "user"]


def test_model_call_rewrites_system_replay_for_codex_multi_provider_unknown_prefix_model_id() -> None:
    agent = Agent(name="A", instructions="normal agent instructions", model="anthropic/foo")
    run_config = RunConfig(
        model_provider=_multi_provider_unknown_prefix_model_id(CODEX_BASE_URL),
    )

    assert _model_call_roles(agent, run_config) == ["developer", "developer", "developer", "user"]


def test_model_call_keeps_system_replay_for_non_codex_openai_provider_run_config() -> None:
    agent = Agent(name="A", instructions="normal agent instructions", model="gpt-5.4-mini")
    run_config = RunConfig(
        model_provider=OpenAIProvider(api_key="sk-test", base_url=OPENAI_BASE_URL),
    )

    assert _model_call_roles(agent, run_config) == ["system", "system", "system", "user"]


def test_model_call_rewrites_system_replay_for_non_codex_openai_provider_base_url_with_codex_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agency_swarm.messages import codex_input

    agent = Agent(name="A", instructions="normal agent instructions", model="gpt-5.4-mini")
    run_config = RunConfig(
        model_provider=OpenAIProvider(api_key="sk-test", base_url=OPENAI_BASE_URL),
    )
    monkeypatch.setattr(
        codex_input, "get_default_openai_client", lambda: AsyncOpenAI(api_key="sk-test", base_url=CODEX_BASE_URL)
    )

    assert _model_call_roles(agent, run_config) == ["developer", "developer", "developer", "user"]


def test_model_call_keeps_system_replay_for_explicit_non_openai_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agency_swarm.messages import codex_input

    agent = Agent(name="A", instructions="normal agent instructions", model="gpt-5.4-mini")
    run_config = RunConfig(model_provider=_NonOpenAIProvider())
    monkeypatch.setattr(
        codex_input, "get_default_openai_client", lambda: AsyncOpenAI(api_key="sk-test", base_url=CODEX_BASE_URL)
    )

    assert _model_call_roles(agent, run_config) == ["system", "system", "system", "user"]


def test_model_call_keeps_system_replay_for_explicit_non_openai_provider_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agency_swarm.messages import codex_input

    agent = Agent(name="A", instructions="normal agent instructions", model=None)
    run_config = RunConfig(model_provider=_NonOpenAIProvider())
    monkeypatch.setattr(
        codex_input, "get_default_openai_client", lambda: AsyncOpenAI(api_key="sk-test", base_url=CODEX_BASE_URL)
    )

    assert _model_call_roles(agent, run_config) == ["system", "system", "system", "user"]


def test_model_call_keeps_system_replay_for_explicit_non_codex_openai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agency_swarm.messages import codex_input

    agent = Agent(name="A", instructions="normal agent instructions", model="gpt-5.4-mini")
    run_config = RunConfig(
        model_provider=OpenAIProvider(openai_client=AsyncOpenAI(api_key="sk-test", base_url=OPENAI_BASE_URL)),
    )
    monkeypatch.setattr(
        codex_input, "get_default_openai_client", lambda: AsyncOpenAI(api_key="sk-test", base_url=CODEX_BASE_URL)
    )

    assert _model_call_roles(agent, run_config) == ["system", "system", "system", "user"]


def test_model_call_keeps_system_replay_for_custom_model_with_codex_cached_client() -> None:
    from tests.deterministic_model import DeterministicModel

    agent = Agent(
        name="A",
        instructions="normal agent instructions",
        model=DeterministicModel(model="anthropic/claude-sonnet-4"),
    )
    agent._openai_client = AsyncOpenAI(api_key="sk-test", base_url=CODEX_BASE_URL)

    assert _model_call_roles(agent, RunConfig()) == ["system", "system", "system", "user"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("base_url", "expected_reminder_role"),
    [
        (CODEX_BASE_URL, "developer"),
        (OPENAI_BASE_URL, "system"),
    ],
)
async def test_handoff_target_model_call_rewrites_codex_reminder_without_mutating_history(
    base_url: str,
    expected_reminder_role: str,
) -> None:
    target_model = _CapturingResponsesModel(base_url=base_url)
    coordinator = Agent(
        name="Coordinator",
        instructions="Hand off Worker tasks.",
        model=DeterministicModel(),
    )
    worker = Agent(
        name="Worker",
        instructions="Handle transferred tasks.",
        model=target_model,
    )
    agency = Agency(coordinator, communication_flows=[(coordinator, worker, Handoff)])

    result = await agency.get_response("Please transfer this to Worker.")

    assert result.final_output == "worker done"
    assert target_model.inputs
    reminder_roles = [
        message["role"]
        for message in target_model.inputs[-1]
        if message.get("content") == "Transfer completed. You are Worker. Please continue the task."
    ]
    assert reminder_roles == [expected_reminder_role]

    stored_reminders = [
        message
        for message in agency.thread_manager.get_all_messages()
        if message.get("message_origin") == "handoff_reminder"
    ]
    assert _roles(stored_reminders) == ["system"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("base_url", "expected_model_roles"),
    [
        (CODEX_BASE_URL, ["developer", "developer", "developer", "user"]),
        (OPENAI_BASE_URL, ["system", "system", "system", "user"]),
    ],
)
async def test_response_endpoint_keeps_runner_input_and_filters_model_call_boundary(
    monkeypatch: pytest.MonkeyPatch,
    base_url: str,
    expected_model_roles: list[str],
) -> None:
    pytest.importorskip("agents")

    import agents

    captured: dict[str, Any] = {}

    async def _run(**kwargs: Any) -> _RunResult:
        captured["input"] = cast(list[dict[str, Any]], kwargs["input"])
        captured["run_config"] = kwargs["run_config"]
        captured["starting_agent"] = kwargs["starting_agent"]
        captured["model_roles"] = await _filtered_roles(
            kwargs["run_config"],
            kwargs["starting_agent"],
            captured["input"],
        )
        assert kwargs["starting_agent"].instructions == "normal agent instructions"
        return _RunResult()

    monkeypatch.setattr(agents.Runner, "run", _run)
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers", _attach_noop
    )

    replayed = _history()
    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)
    response = await handler(
        BaseRequest(
            message="next",
            chat_history=replayed,
            client_config=ClientConfig(api_key="sk-test", base_url=base_url),
        ),
        token=None,
    )

    assert response["response"] == "ok"
    assert _roles(captured["input"]) == ["system", "system", "system", "user"]
    assert captured["model_roles"] == expected_model_roles
    assert _roles(replayed) == ["system", "system", "system"]


@pytest.mark.asyncio
async def test_response_endpoint_keeps_system_replay_for_custom_model_with_codex_cached_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("agents")

    import agents

    from tests.deterministic_model import DeterministicModel

    captured: dict[str, Any] = {}

    async def _run(**kwargs: Any) -> _RunResult:
        starting_agent = kwargs["starting_agent"]
        captured["input"] = cast(list[dict[str, Any]], kwargs["input"])
        captured["run_config"] = kwargs["run_config"]
        captured["starting_agent"] = starting_agent
        captured["model_roles"] = await _filtered_roles(
            kwargs["run_config"],
            starting_agent,
            captured["input"],
        )
        assert starting_agent.model.model == "anthropic/claude-sonnet-4"
        assert str(starting_agent._openai_client.base_url).rstrip("/") == CODEX_BASE_URL
        return _RunResult()

    def _custom_model_agency_factory(**kwargs: Any) -> Agency:
        return Agency(
            Agent(
                name="A",
                instructions="normal agent instructions",
                model=DeterministicModel(model="anthropic/claude-sonnet-4"),
            ),
            load_threads_callback=kwargs["load_threads_callback"],
        )

    monkeypatch.setattr(agents.Runner, "run", _run)
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers", _attach_noop
    )

    replayed = _history()
    handler = make_response_endpoint(BaseRequest, _custom_model_agency_factory, verify_token=lambda: None)
    response = await handler(
        BaseRequest(
            message="next",
            chat_history=replayed,
            client_config=ClientConfig(api_key="sk-test", base_url=CODEX_BASE_URL),
        ),
        token=None,
    )

    assert response["response"] == "ok"
    assert _roles(captured["input"]) == ["system", "system", "system", "user"]
    assert captured["model_roles"] == ["system", "system", "system", "user"]
    assert _roles(replayed) == ["system", "system", "system"]


@pytest.mark.asyncio
async def test_stream_endpoint_keeps_runner_input_and_filters_model_call_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("agents")

    import agents

    captured: dict[str, Any] = {}

    def _run_streamed(**kwargs: Any) -> _StreamedResult:
        captured["input"] = cast(list[dict[str, Any]], kwargs["input"])
        captured["run_config"] = kwargs["run_config"]
        captured["starting_agent"] = kwargs["starting_agent"]
        assert kwargs["starting_agent"].instructions == "normal agent instructions"
        return _StreamedResult()

    monkeypatch.setattr(agents.Runner, "run_streamed", _run_streamed)
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers", _attach_noop
    )

    replayed = _history()
    handler = make_stream_endpoint(
        BaseRequest, _agency_factory, verify_token=lambda: None, run_registry=ActiveRunRegistry()
    )
    response = await handler(
        http_request=_HttpRequest(),
        request=BaseRequest(
            message="next",
            chat_history=replayed,
            client_config=ClientConfig(api_key="sk-test", base_url=CODEX_BASE_URL),
        ),
        token=None,
    )
    chunks = [chunk async for chunk in response.body_iterator]

    assert chunks[-1] == "event: end\ndata: [DONE]\n\n"
    assert _roles(captured["input"]) == ["system", "system", "system", "user"]
    assert captured["run_config"].call_model_input_filter is not None
    assert _roles(replayed) == ["system", "system", "system"]


@pytest.mark.asyncio
async def test_response_endpoint_rewrites_codex_system_replay_for_default_openai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("agents")

    import agents
    from openai import AsyncOpenAI

    from agency_swarm.messages import codex_input

    captured: dict[str, Any] = {}

    async def _run(**kwargs: Any) -> _RunResult:
        captured["input"] = cast(list[dict[str, Any]], kwargs["input"])
        captured["run_config"] = kwargs["run_config"]
        captured["starting_agent"] = kwargs["starting_agent"]
        captured["model_roles"] = await _filtered_roles(
            kwargs["run_config"],
            kwargs["starting_agent"],
            captured["input"],
        )
        return _RunResult()

    monkeypatch.setattr(agents.Runner, "run", _run)
    monkeypatch.setattr(
        codex_input, "get_default_openai_client", lambda: AsyncOpenAI(api_key="sk-test", base_url=CODEX_BASE_URL)
    )
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers", _attach_noop
    )

    replayed = _history()
    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)
    response = await handler(BaseRequest(message="next", chat_history=replayed), token=None)

    assert response["response"] == "ok"
    assert _roles(captured["input"]) == ["system", "system", "system", "user"]
    assert captured["model_roles"] == ["developer", "developer", "developer", "user"]


@pytest.mark.asyncio
async def test_agui_endpoint_keeps_runner_input_and_filters_model_call_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("agents")

    import agents

    captured: dict[str, Any] = {}

    def _run_streamed(**kwargs: Any) -> _StreamedResult:
        captured["input"] = cast(list[dict[str, Any]], kwargs["input"])
        captured["run_config"] = kwargs["run_config"]
        captured["starting_agent"] = kwargs["starting_agent"]
        assert kwargs["starting_agent"].instructions == "normal agent instructions"
        return _StreamedResult()

    monkeypatch.setattr(agents.Runner, "run_streamed", _run_streamed)
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers", _attach_noop
    )

    replayed = _history()
    handler = make_agui_chat_endpoint(RunAgentInputCustom, _agency_factory, verify_token=lambda: None)
    response = await handler(
        RunAgentInputCustom(
            thread_id="thread-1",
            run_id="run-1",
            state=None,
            messages=[{"id": "msg-1", "role": "user", "content": "next"}],
            tools=[],
            context=[],
            forwarded_props=None,
            chat_history=replayed,
            client_config=ClientConfig(api_key="sk-test", base_url=CODEX_BASE_URL),
        ),
        token=None,
    )
    chunks = [chunk async for chunk in response.body_iterator]

    assert chunks
    assert _roles(captured["input"]) == ["system", "system", "system", "user"]
    assert captured["run_config"].call_model_input_filter is not None
    assert _roles(replayed) == ["system", "system", "system"]


@pytest.mark.asyncio
async def test_generate_chat_name_rewrites_codex_system_input_before_direct_responses_create() -> None:
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers

    captured: dict[str, Any] = {}

    class _Event:
        def __init__(self, delta: str) -> None:
            self.type = "response.output_text.delta"
            self.delta = delta

    class _DummyResponse:
        def __aiter__(self) -> AsyncGenerator[_Event]:
            return self._events()

        async def _events(self) -> AsyncGenerator[_Event]:
            yield _Event("Replay")
            yield _Event(" Title")

    class _DummyResponses:
        async def create(self, **kwargs: Any) -> _DummyResponse:
            captured.update(kwargs)
            return _DummyResponse()

    class _DummyClient:
        base_url = CODEX_BASE_URL
        responses = _DummyResponses()

    result = await endpoint_handlers.generate_chat_name(
        [
            {"role": "system", "content": "replayed context", "agent": "A", "callerAgent": None},
            {"role": "user", "content": "next", "agent": "A", "callerAgent": None},
        ],
        openai_client=_DummyClient(),
    )

    assert result == "Replay Title"
    assert _roles(captured["input"]) == ["developer", "user"]

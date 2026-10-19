"""Pure configuration checks for endpoint-aware tracing defaults."""

import pytest
from agents import (
    Agent as SDKAgent,
    Model,
    ModelProvider,
    OpenAIChatCompletionsModel,
    OpenAIResponsesModel,
    RunConfig,
    RunContextWrapper,
    handoff,
)
from agents.models import _openai_shared
from agents.models.multi_provider import MultiProvider
from agents.models.openai_provider import OpenAIProvider
from agents.models.openai_responses import OpenAIResponsesWSModel
from agents.run_state import RunState
from agents.tracing import setup as trace_setup
from agents.tracing.processors import default_processor
from agents.tracing.provider import DefaultTraceProvider
from openai import AsyncOpenAI

from agency_swarm import Agent, MasterContext
from agency_swarm.agent.tracing import with_endpoint_tracing_defaults
from agency_swarm.utils.thread import ThreadManager
from tests.deterministic_model import DeterministicModel


@pytest.fixture(autouse=True)
def clean_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_AGENTS_DISABLE_TRACING", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-offline-test")
    provider = DefaultTraceProvider()
    provider.register_processor(default_processor())
    monkeypatch.setattr(trace_setup, "GLOBAL_TRACE_PROVIDER", provider)


@pytest.mark.parametrize("model_type", [OpenAIResponsesModel, OpenAIChatCompletionsModel])
@pytest.mark.parametrize(
    ("endpoint", "disabled"),
    [
        ("https://api.openai.com/v1", False),
        ("https://api.openai.com:443/v1/", False),
        ("http://127.0.0.1:9999/v1", True),
        ("https://proxy.example/v1", True),
        ("https://api.openai.com.evil.example/v1", True),
        ("https://api.openai.com@evil.example/v1", True),
        ("https://api.openai.com:8443/v1", True),
        ("http://api.openai.com/v1", True),
    ],
)
def test_actual_endpoint_origin_controls_default(model_type: type, endpoint: str, disabled: bool) -> None:
    client = AsyncOpenAI(api_key="sk-offline-test", base_url=endpoint)
    agent = SDKAgent(name="Probe", model=model_type(model="gpt-4o-mini", openai_client=client))
    config = RunConfig(workflow_name="preserved", trace_metadata={"purpose": "test"})
    result = with_endpoint_tracing_defaults(agent, config)
    assert result.tracing_disabled is disabled
    assert config.tracing_disabled is False
    assert result.workflow_name == "preserved"
    assert result.trace_metadata == {"purpose": "test"}


@pytest.mark.parametrize("flag", ["0", "false", "FALSE", "1", "true", "TRUE"])
def test_explicit_env_choice_is_left_to_sdk(monkeypatch: pytest.MonkeyPatch, flag: str) -> None:
    monkeypatch.setenv("OPENAI_AGENTS_DISABLE_TRACING", flag)
    agent = SDKAgent(name="Probe", model="gpt-4o-mini")
    config = RunConfig()
    assert with_endpoint_tracing_defaults(agent, config) is config


@pytest.mark.parametrize("provider_kind", ["openai", "multi"])
def test_provider_endpoint_beats_environment(monkeypatch: pytest.MonkeyPatch, provider_kind: str) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
    if provider_kind == "openai":
        provider = OpenAIProvider(api_key="sk-offline-test", base_url="https://api.openai.com/v1")
    else:
        provider = MultiProvider(openai_api_key="sk-offline-test", openai_base_url="https://api.openai.com/v1")
    agent = SDKAgent(name="Probe", model="gpt-4o-mini")
    config = RunConfig(model_provider=provider)
    assert with_endpoint_tracing_defaults(agent, config) is config


class _PrivateEndpointProvider(ModelProvider):
    def get_model(self, model_name: str | None) -> Model:
        raise AssertionError("Endpoint inspection must not resolve arbitrary providers")


def test_unknown_provider_is_not_probed() -> None:
    agent = SDKAgent(name="Probe", model="private/model")
    config = RunConfig(model_provider=_PrivateEndpointProvider())
    assert with_endpoint_tracing_defaults(agent, config) is config


@pytest.mark.parametrize("route", ["model", "provider", "multi_provider"])
@pytest.mark.parametrize(
    ("http_base", "ws_base", "disabled"),
    [
        ("https://api.openai.com/v1", "wss://proxy.example/v1", True),
        ("https://proxy.example/v1", "wss://api.openai.com/v1", False),
    ],
)
def test_websocket_endpoint_controls_default(route: str, http_base: str, ws_base: str, disabled: bool) -> None:
    client = AsyncOpenAI(api_key="sk-offline-test", base_url=http_base, websocket_base_url=ws_base)
    agent = SDKAgent(name="Probe", model="gpt-4o-mini")
    config = RunConfig()
    if route == "model":
        agent.model = OpenAIResponsesWSModel("gpt-4o-mini", openai_client=client)
    elif route == "provider":
        config = RunConfig(model_provider=OpenAIProvider(openai_client=client, use_responses_websocket=True))
    else:
        config = RunConfig(model_provider=MultiProvider(openai_client=client, openai_use_responses_websocket=True))
    assert with_endpoint_tracing_defaults(agent, config).tracing_disabled is disabled


def test_endpoint_inspection_keeps_provider_client_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY")
    provider = OpenAIProvider(base_url="http://127.0.0.1:9999/v1")
    agent = SDKAgent(name="Probe", model="gpt-4o-mini")
    assert with_endpoint_tracing_defaults(agent, RunConfig(model_provider=provider)).tracing_disabled
    assert provider._client is None


@pytest.mark.parametrize("context_kind", ["direct", "wrapped", "resumed"])
@pytest.mark.parametrize("parent_model_override", [False, True])
def test_agency_children_use_their_own_model_config(context_kind: str, parent_model_override: bool) -> None:
    native_model = OpenAIResponsesModel(
        "gpt-4o-mini",
        openai_client=AsyncOpenAI(api_key="sk-offline-test", base_url="https://api.openai.com/v1"),
    )
    proxy_model = OpenAIResponsesModel(
        "gpt-4o-mini",
        openai_client=AsyncOpenAI(api_key="sk-offline-test", base_url="http://127.0.0.1:9999/v1"),
    )
    native = Agent(name="Native", model=native_model)
    proxy = Agent(name="Proxy", model=proxy_model)
    context = MasterContext(thread_manager=ThreadManager(), agents={"Native": native, "Proxy": proxy})
    config = RunConfig(model=native_model) if parent_model_override else RunConfig()
    state = RunState(RunContextWrapper(context), "Resume", starting_agent=native) if context_kind == "resumed" else None
    explicit_context = (
        None if state is not None else (RunContextWrapper(context) if context_kind == "wrapped" else context)
    )
    result = with_endpoint_tracing_defaults(native, config, run_state=state, context=explicit_context)
    assert result.tracing_disabled is True
    assert config.tracing_disabled is False


@pytest.mark.parametrize("disabled", [False, True])
def test_manual_sdk_choice_is_preserved(monkeypatch: pytest.MonkeyPatch, disabled: bool) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
    provider = trace_setup.get_trace_provider()
    provider.set_disabled(disabled)
    config = RunConfig()
    assert with_endpoint_tracing_defaults(SDKAgent(name="Probe"), config) is config


def test_replaced_processors_are_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
    trace_setup.get_trace_provider().set_processors([])
    config = RunConfig()
    assert with_endpoint_tracing_defaults(SDKAgent(name="Probe"), config) is config


@pytest.mark.parametrize("config", [RunConfig(tracing_disabled=True), RunConfig(tracing={"api_key": "sk-offline"})])
def test_explicit_run_tracing_is_preserved(monkeypatch: pytest.MonkeyPatch, config: RunConfig) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
    assert with_endpoint_tracing_defaults(SDKAgent(name="Probe"), config) is config


def test_other_model_types_keep_sdk_behavior() -> None:
    agent = SDKAgent(name="Probe", model=DeterministicModel())
    config = RunConfig()
    assert with_endpoint_tracing_defaults(agent, config) is config


@pytest.mark.parametrize("explicit_key", [False, True])
def test_explicit_provider_options_override_default_client(monkeypatch: pytest.MonkeyPatch, explicit_key: bool) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
    native = AsyncOpenAI(api_key="sk-offline-test", base_url="https://api.openai.com/v1")
    monkeypatch.setattr(_openai_shared, "_default_openai_client", native)
    provider = OpenAIProvider(api_key="sk-offline-test") if explicit_key else OpenAIProvider()
    config = RunConfig(model_provider=provider)
    result = with_endpoint_tracing_defaults(SDKAgent(name="Probe"), config)
    assert result.tracing_disabled is explicit_key
    assert provider._client is None


@pytest.mark.parametrize("name", ["openai/gpt-4o-mini", "vendor/model"])
def test_sdk_prefix_modes_are_respected(name: str) -> None:
    provider = MultiProvider(
        openai_base_url="http://127.0.0.1:9999/v1",
        unknown_prefix_mode="model_id",
        openai_prefix_mode="model_id",
    )
    config = RunConfig(model_provider=provider)
    assert with_endpoint_tracing_defaults(SDKAgent(name="Probe", model=name), config).tracing_disabled


@pytest.mark.parametrize("disabled_handoff", [False, True])
def test_cyclic_handoffs_and_disabled_targets(disabled_handoff: bool) -> None:
    native = SDKAgent(
        name="Native",
        model=OpenAIResponsesModel(
            "gpt-4o-mini",
            openai_client=AsyncOpenAI(api_key="sk-offline-test", base_url="https://api.openai.com/v1"),
        ),
    )
    proxy = SDKAgent(
        name="Proxy",
        model=OpenAIResponsesModel(
            "gpt-4o-mini",
            openai_client=AsyncOpenAI(api_key="sk-offline-test", base_url="http://127.0.0.1:9999/v1"),
        ),
    )
    native.handoffs = [handoff(proxy, is_enabled=not disabled_handoff)]
    proxy.handoffs = [native]
    assert with_endpoint_tracing_defaults(native, RunConfig()).tracing_disabled is not disabled_handoff

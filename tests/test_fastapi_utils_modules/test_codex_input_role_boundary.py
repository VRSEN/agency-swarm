import inspect

import pytest
from agents import RunConfig
from agents.models.multi_provider import MultiProvider, MultiProviderMap
from agents.models.openai_provider import OpenAIProvider
from openai import AsyncOpenAI

from agency_swarm import Agency, Agent
from agency_swarm.tools import Handoff
from tests.deterministic_model import DeterministicModel
from tests.test_fastapi_utils_modules._codex_input_role_boundary_helpers import (
    CODEX_BASE_URL,
    OPENAI_BASE_URL,
    _CapturingResponsesModel,
    _model_call_roles,
    _NonOpenAIProvider,
    _roles,
)


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

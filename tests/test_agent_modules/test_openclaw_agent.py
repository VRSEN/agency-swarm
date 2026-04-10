from __future__ import annotations

from pathlib import Path

import pytest
from agents.models.openai_responses import OpenAIResponsesModel

from agency_swarm import Agency, Agent, OpenClawAgent
from agency_swarm.integrations import openclaw_model as openclaw_model_mod
from agency_swarm.integrations.openclaw_model import (
    build_openclaw_responses_model,
    register_current_app_openclaw_defaults,
)
from agency_swarm.tools.send_message import Handoff
from agency_swarm.utils.model_utils import (
    get_default_settings_model_name,
    get_model_name,
    get_usage_tracking_model_name,
)


def test_openclaw_agent_auto_builds_responses_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCLAW_PROXY_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setenv("OPENCLAW_PROVIDER_MODEL", "openai/gpt-5.4-mini")

    agent = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
    )

    assert isinstance(agent.model, OpenAIResponsesModel)
    assert agent.model.model == "openclaw:main"
    assert get_model_name(agent.model) == "openclaw:main"
    assert get_usage_tracking_model_name(agent.model) == "openai/gpt-5.4-mini"
    assert str(agent.model._client.base_url) == "http://127.0.0.1:8000/openclaw/v1/"
    assert agent.supports_outbound_communication is False
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "low"
    assert agent.model_settings.verbosity == "low"


def test_openclaw_agent_supports_custom_host_port_and_path() -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("OPENCLAW_PROXY_BASE_URL", "http://env.example/openclaw/v1")
        agent = OpenClawAgent(
            name="OpenClawWorker",
            description="Worker",
            instructions="Handle OpenClaw work.",
            host="127.0.0.1",
            port=18080,
            api_path="/worker/v1",
        )

    assert str(agent.model._client.base_url) == "http://127.0.0.1:18080/worker/v1/"
    assert agent.model.model == "openclaw:main"


@pytest.mark.parametrize(
    ("kwargs", "expected_url"),
    [
        ({"api_path": "/worker/v1"}, "https://proxy.example/worker/v1/"),
        ({"host": "worker.example"}, "https://worker.example/openclaw/v1/"),
        ({"port": 9443}, "https://proxy.example:9443/openclaw/v1/"),
    ],
)
def test_openclaw_agent_preserves_env_proxy_base_url_when_partially_overridden(
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, str | int],
    expected_url: str,
) -> None:
    monkeypatch.setenv("OPENCLAW_PROXY_BASE_URL", "https://proxy.example/openclaw/v1")

    agent = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
        api_key="external-token",
        **kwargs,
    )

    assert str(agent.model._client.base_url) == expected_url


def test_openclaw_agent_defaults_external_v1_urls_to_provider_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_PROVIDER_MODEL", "anthropic/claude-sonnet-4-5")

    agent = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
        base_url="http://127.0.0.1:18789/v1",
        api_key="external-token",
    )

    assert str(agent.model._client.base_url) == "http://127.0.0.1:18789/v1/"
    assert agent.model.model == "anthropic/claude-sonnet-4-5"


def test_build_openclaw_responses_model_defaults_raw_gateway_to_local_runtime_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_API_KEY", raising=False)
    monkeypatch.delenv("APP_TOKEN", raising=False)

    model = build_openclaw_responses_model(base_url="http://127.0.0.1:18789/v1")

    assert model._client.api_key == "openclaw-local-token"


@pytest.mark.parametrize(
    "base_url",
    [
        "https://example.com/openclaw/v1",
        "http://127.0.0.1:18789/v1",
    ],
)
def test_openclaw_agent_preserves_model_alias_override_for_external_servers(base_url: str) -> None:
    agent = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
        base_url=base_url,
        api_key="external-token",
        model="openclaw:custom",
    )

    assert str(agent.model._client.base_url) == f"{base_url}/"
    assert agent.model.model == "openclaw:custom"


def test_build_openclaw_responses_model_preserves_explicit_alias_for_direct_gateway_urls() -> None:
    model = build_openclaw_responses_model(
        model="openclaw:custom",
        base_url="http://127.0.0.1:18789/v1",
        api_key="external-token",
    )

    assert model.model == "openclaw:custom"
    assert get_usage_tracking_model_name(model) == "openclaw:custom"
    assert get_default_settings_model_name(model) == "openclaw:custom"


def test_openclaw_agent_uses_gateway_token_before_app_token_for_direct_gateway_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_PROXY_API_KEY", "proxy-token")
    monkeypatch.setenv("APP_TOKEN", "app-token")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "gateway-token")

    agent = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
        base_url="http://127.0.0.1:18789/v1",
    )

    assert agent.model._client.api_key == "gateway-token"


def test_openclaw_agent_keeps_app_token_first_for_local_proxy_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCLAW_PROXY_API_KEY", raising=False)
    monkeypatch.setenv("APP_TOKEN", "app-token")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "gateway-token")

    agent = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
    )

    assert agent.model._client.api_key == "app-token"


def test_openclaw_agent_treats_localhost_proxy_aliases_as_current_app_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENCLAW_PROXY_API_KEY", raising=False)
    monkeypatch.delenv("OPENCLAW_PROVIDER_MODEL", raising=False)
    monkeypatch.setenv("APP_TOKEN", "app-token")
    monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN", raising=False)
    monkeypatch.setenv("OPENCLAW_PROXY_BASE_URL", "http://127.0.0.1:8000/openclaw/v1")
    monkeypatch.setattr(openclaw_model_mod, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)
    monkeypatch.setattr(openclaw_model_mod, "_CURRENT_APP_OPENCLAW_DEFAULT_COUNTS", {}, raising=False)
    monkeypatch.setattr(openclaw_model_mod, "_CURRENT_APP_OPENCLAW_DEFAULT_PATTERNS", [], raising=False)
    monkeypatch.setattr(openclaw_model_mod, "_CURRENT_APP_OPENCLAW_DEFAULT_PATTERN_COUNTS", {}, raising=False)

    model = build_openclaw_responses_model(base_url="http://localhost:8000/openclaw/v1")

    assert model._client.api_key == "app-token"
    assert get_usage_tracking_model_name(model) == "openai/gpt-5.4"


def test_openclaw_agent_uses_app_token_for_explicit_same_app_proxy_url_when_one_current_app_proxy_is_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_PROXY_API_KEY", "proxy-token")
    monkeypatch.setenv("OPENCLAW_PROXY_BASE_URL", "http://127.0.0.1:9000/openclaw/v1")
    monkeypatch.setenv("APP_TOKEN", "app-token")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "gateway-token")
    monkeypatch.setattr(openclaw_model_mod, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)
    register_current_app_openclaw_defaults(
        default_model="openclaw:custom",
        provider_model="openai/gpt-5.4-mini",
        base_url="http://127.0.0.1:9000/openclaw/v1",
    )

    agent = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
        host="127.0.0.1",
        port=9000,
    )

    assert agent.model.model == "openclaw:custom"
    assert agent.model._client.api_key == "app-token"


def test_openclaw_agent_rejects_manual_handoffs() -> None:
    recipient = Agent(
        name="Recipient",
        description="Recipient",
        instructions="Return the result.",
        model="gpt-5.4-mini",
    )

    with pytest.raises(TypeError, match="does not accept manual handoffs"):
        OpenClawAgent(
            name="OpenClawWorker",
            description="Worker",
            instructions="Handle OpenClaw work.",
            handoffs=[Handoff().create_handoff(recipient)],
        )


def test_openclaw_agent_rejects_framework_tool_wiring() -> None:
    with pytest.raises(TypeError, match="does not accept Agency Swarm tool wiring"):
        OpenClawAgent(
            name="OpenClawWorker",
            description="Worker",
            instructions="Handle OpenClaw work.",
            tools=[object()],
        )


def test_openclaw_agent_rejects_files_folder_tool_wiring() -> None:
    with pytest.raises(TypeError, match="does not accept Agency Swarm tool wiring"):
        OpenClawAgent(
            name="OpenClawWorker",
            description="Worker",
            instructions="Handle OpenClaw work.",
            files_folder="./files",
        )


def test_openclaw_agent_rejects_manual_communication_capability_overrides() -> None:
    with pytest.raises(TypeError, match="always receive-only"):
        OpenClawAgent(
            name="OpenClawWorker",
            description="Worker",
            instructions="Handle OpenClaw work.",
            supports_outbound_communication=True,
        )


def test_openclaw_agent_skips_shared_tool_wiring() -> None:
    openclaw_worker = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
    )
    coordinator = Agent(
        name="Coordinator",
        description="Coordinator",
        instructions="Coordinate the work.",
        model="gpt-5.4-mini",
    )

    agency = Agency(
        coordinator,
        communication_flows=[(coordinator, openclaw_worker)],
        shared_tools=[object()],
    )

    assert agency.agents["OpenClawWorker"].supports_framework_tool_wiring is False


def test_openclaw_agent_skips_shared_file_preprocessing_when_no_agent_supports_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    shared_files = tmp_path / "shared-files"
    shared_files.mkdir()
    (shared_files / "notes.txt").write_text("hello", encoding="utf-8")

    openclaw_worker = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
    )

    agency = Agency(openclaw_worker, shared_files_folder=str(shared_files))

    assert agency.agents["OpenClawWorker"].supports_framework_tool_wiring is False


def test_openclaw_agent_cannot_register_subagent() -> None:
    agent = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
    )
    recipient = Agent(
        name="Recipient",
        description="Recipient",
        instructions="Return the result.",
        model="gpt-5.4-mini",
    )

    with pytest.raises(ValueError, match="cannot register subagents because it is configured as receive-only"):
        agent.register_subagent(recipient)


def test_openclaw_agent_cannot_be_sender_in_communication_flows() -> None:
    openclaw_worker = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
    )
    specialist = Agent(
        name="Specialist",
        description="Specialist",
        instructions="Return the result.",
        model="gpt-5.4-mini",
    )

    with pytest.raises(ValueError, match="cannot be the sender in communication_flows"):
        Agency(openclaw_worker, communication_flows=[(openclaw_worker, specialist)])

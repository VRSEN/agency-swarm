from __future__ import annotations

from pathlib import Path

import pytest
from agents.models.openai_responses import OpenAIResponsesModel

from agency_swarm import Agency, Agent, OpenClawAgent
from agency_swarm.tools.send_message import Handoff
from agency_swarm.utils.model_utils import get_model_name, get_usage_tracking_model_name


def test_openclaw_agent_auto_builds_responses_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCLAW_PROXY_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setenv("OPENCLAW_PROVIDER_MODEL", "openai/gpt-5.4")

    agent = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
    )

    assert isinstance(agent.model, OpenAIResponsesModel)
    assert agent.model.model == "openclaw:main"
    assert get_model_name(agent.model) == "openclaw:main"
    assert get_usage_tracking_model_name(agent.model) == "openai/gpt-5.4"
    assert str(agent.model._client.base_url) == "http://127.0.0.1:8000/openclaw/v1/"
    assert agent.supports_outbound_communication is False


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


def test_openclaw_agent_brackets_ipv6_hosts() -> None:
    agent = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
        host="::1",
        port=18080,
    )

    assert str(agent.model._client.base_url) == "http://[::1]:18080/openclaw/v1/"


def test_openclaw_agent_defaults_external_v1_urls_to_public_alias() -> None:
    agent = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
        base_url="http://127.0.0.1:18789/v1",
        api_key="external-token",
    )

    assert str(agent.model._client.base_url) == "http://127.0.0.1:18789/v1/"
    assert agent.model.model == "openclaw:main"


def test_openclaw_agent_uses_gateway_token_when_proxy_key_and_app_token_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENCLAW_PROXY_API_KEY", raising=False)
    monkeypatch.delenv("APP_TOKEN", raising=False)
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "gateway-token")

    agent = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
    )

    assert agent.model._client.api_key == "gateway-token"


def test_openclaw_agent_uses_gateway_token_before_app_token_for_direct_gateway_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENCLAW_PROXY_API_KEY", raising=False)
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


def test_openclaw_agent_uses_gateway_token_for_external_openclaw_proxy_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENCLAW_PROXY_API_KEY", raising=False)
    monkeypatch.setenv("APP_TOKEN", "app-token")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "gateway-token")

    agent = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
        base_url="https://example.com/openclaw/v1",
    )

    assert agent.model._client.api_key == "gateway-token"


def test_openclaw_agent_rejects_manual_handoffs() -> None:
    recipient = Agent(
        name="Recipient",
        description="Recipient",
        instructions="Return the result.",
        model="gpt-5.4",
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
        model="gpt-5.4",
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
        model="gpt-5.4",
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
        model="gpt-5.4",
    )

    with pytest.raises(ValueError, match="cannot be the sender in communication_flows"):
        Agency(openclaw_worker, communication_flows=[(openclaw_worker, specialist)])

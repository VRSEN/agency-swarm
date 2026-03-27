"""Minimal tests for FastAPI request models that include `client_config`.

The end-to-end behavior is covered in integration tests under `tests/integration/fastapi/`.
"""

import pytest
from pydantic import ValidationError

from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"base_url": "https://custom.api.com", "api_key": "sk-custom-key"},
            {"base_url": "https://custom.api.com", "api_key": "sk-custom-key"},
        ),
        (
            {"base_url": "https://custom.api.com"},
            {"base_url": "https://custom.api.com", "api_key": None},
        ),
        (
            {"api_key": "sk-custom-key"},
            {"base_url": None, "api_key": "sk-custom-key"},
        ),
        (
            {},
            {"base_url": None, "api_key": None, "default_headers": None, "litellm_keys": None},
        ),
    ],
)
def test_client_config_accepts_optional_overrides(payload: dict, expected: dict) -> None:
    """Client config should accept partial override payloads without extra scaffolding."""
    config = ClientConfig(**payload)
    for key, value in expected.items():
        assert getattr(config, key) == value


def test_client_config_accepts_litellm_keys_when_available() -> None:
    """litellm_keys should validate when LiteLLM is installed."""
    try:
        config = ClientConfig(
            litellm_keys={
                "anthropic": "sk-ant-xxx",
                "gemini": "AIza...",
            }
        )
    except ValidationError as exc:
        assert "litellm_keys requires litellm to be installed" in str(exc)
        return
    assert config.litellm_keys is not None
    assert config.litellm_keys["anthropic"] == "sk-ant-xxx"
    assert config.litellm_keys["gemini"] == "AIza..."


def test_base_request_client_config_roundtrip() -> None:
    """Base request should preserve parsed client_config values."""
    request = BaseRequest(
        message="Hello",
        client_config=ClientConfig(
            base_url="https://custom.api.com",
            api_key="sk-custom-key",
            default_headers={"x-test": "1"},
        ),
    )
    assert request.client_config is not None
    assert request.client_config.base_url == "https://custom.api.com"
    assert request.client_config.api_key == "sk-custom-key"
    assert request.client_config.default_headers == {"x-test": "1"}


def test_request_api_key_allows_client_build_without_env(monkeypatch) -> None:
    """Request api_key should work even if server has no OPENAI_API_KEY."""
    pytest.importorskip("agents")

    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Common setup: model is a plain string, so there is no embedded OpenAI client.
    agent = Agent(name="TestAgent", instructions="x", model="gpt-4o-mini")
    cfg = ClientConfig(api_key="sk-test", base_url="http://example.invalid", default_headers={"x-test": "1"})

    client = endpoint_handlers._build_openai_client_for_agent(agent, cfg)
    assert isinstance(client, AsyncOpenAI)
    assert client.api_key == "sk-test"
    assert str(client.base_url).startswith("http://example.invalid")


def test_default_headers_only_without_baseline_client_falls_back_to_model_settings(monkeypatch) -> None:
    """When there is no baseline client, default_headers must still reach model_settings.extra_headers."""
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    class _AgentState:
        def __init__(self) -> None:
            self.name = "A"
            self.model = "gpt-4o-mini"
            self.model_settings = None

    class _Agency:
        def __init__(self) -> None:
            self.agents = {"A": _AgentState()}

    agency = _Agency()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(endpoint_handlers, "get_default_openai_client", lambda: None)

    apply_openai_client_config(agency, ClientConfig(default_headers={"x-request-id": "req-1"}))

    # Model stays a string — no client was built — but headers must reach model_settings.
    assert agency.agents["A"].model == "gpt-4o-mini"
    assert agency.agents["A"].model_settings is not None
    assert agency.agents["A"].model_settings.extra_headers == {"x-request-id": "req-1"}


def test_default_headers_only_does_not_override_litellm_model_settings() -> None:
    """default_headers-only should not rebuild LitellmModel, and should add headers to model_settings."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    class _Agency:
        def __init__(self, agent: Agent):
            self.agents = {"A": agent}

    original_model = LitellmModel(model="anthropic/claude-sonnet-4", base_url="http://litellm.local", api_key="k1")
    agent = Agent(name="A", instructions="x", model=original_model)
    agency = _Agency(agent)

    apply_openai_client_config(agency, ClientConfig(default_headers={"x-test": "1"}))

    # Must remain intact
    assert isinstance(agent.model, LitellmModel)
    assert agent.model.base_url == "http://litellm.local"
    assert agent.model.api_key == "k1"
    assert agent.model_settings is not None
    assert agent.model_settings.extra_headers is not None
    assert agent.model_settings.extra_headers["x-test"] == "1"


def test_litellm_anthropic_does_not_use_generic_api_key_fallback() -> None:
    """config.api_key should not override Anthropic auth unless litellm_keys is provided."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    class _Agency:
        def __init__(self, agent: Agent):
            self.agents = {"A": agent}

    # Existing LitellmModel has no api_key -> should rely on provider env.
    original_model = LitellmModel(model="anthropic/claude-sonnet-4", base_url="http://litellm.local", api_key=None)
    agent = Agent(name="A", instructions="x", model=original_model)
    agency = _Agency(agent)

    apply_openai_client_config(agency, ClientConfig(api_key="sk-openai-gateway", base_url="http://gw"))

    assert isinstance(agent.model, LitellmModel)
    assert agent.model.model == "anthropic/claude-sonnet-4"
    # Must not be overridden with the OpenAI gateway key.
    assert agent.model.api_key is None


def test_litellm_openai_provider_can_use_generic_api_key_fallback() -> None:
    """For openai-ish LiteLLM providers, config.api_key remains a valid fallback."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    class _Agency:
        def __init__(self, agent: Agent):
            self.agents = {"A": agent}

    original_model = LitellmModel(model="openai/gpt-4o-mini", base_url=None, api_key=None)
    agent = Agent(name="A", instructions="x", model=original_model)
    agency = _Agency(agent)

    apply_openai_client_config(agency, ClientConfig(api_key="sk-openai", base_url="http://gw"))

    assert isinstance(agent.model, LitellmModel)
    assert agent.model.api_key == "sk-openai"


def test_snapshot_restore_preserves_model_settings_headers() -> None:
    """Snapshot/restore should not leak mutated model_settings."""
    pytest.importorskip("agents")

    from agents import ModelSettings

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import (
        _apply_default_headers_to_agent_model_settings,
        _restore_agency_state,
        _snapshot_agency_state,
    )

    class _Agency:
        def __init__(self, agent: Agent):
            self.agents = {"A": agent}

    agent = Agent(name="A", instructions="x", model="gpt-4o-mini")
    agent.model_settings = ModelSettings(extra_headers={"x-orig": "1"})
    agency = _Agency(agent)

    snapshot = _snapshot_agency_state(agency)
    _apply_default_headers_to_agent_model_settings(agent, {"x-orig": "2", "x-new": "3"})

    _restore_agency_state(agency, snapshot)

    assert agent.model_settings.extra_headers == {"x-orig": "1"}


def test_non_openai_custom_model_skips_openai_client_build(monkeypatch) -> None:
    """Custom non-OpenAI model names should skip OpenAI client construction entirely."""
    pytest.importorskip("agents")

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    class _Agency:
        def __init__(self, agent: Agent):
            self.agents = {"A": agent}

    agent = Agent(name="A", instructions="x", model="anthropic/claude-3-5-sonnet")
    agency = _Agency(agent)

    def _boom(*_args, **_kwargs):
        raise AssertionError("_build_openai_client_for_agent should not be called for unsupported models")

    monkeypatch.setattr(endpoint_handlers, "_build_openai_client_for_agent", _boom)

    # Should not raise; unsupported custom models are skipped.
    endpoint_handlers.apply_openai_client_config(agency, ClientConfig(default_headers={"x-test": "1"}))

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
            {
                "base_url": None,
                "api_key": None,
                "default_headers": None,
                "litellm_keys": None,
                "model": None,
            },
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


def test_openai_client_override_applies_codex_compatibility_model_settings() -> None:
    """Codex overrides should use the Responses settings the browser-auth backend accepts."""
    pytest.importorskip("agents")

    from agents import OpenAIResponsesModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    class _Agency:
        def __init__(self, agent: Agent):
            self.agents = {"A": agent}

    agent = Agent(name="A", instructions="x", model="gpt-4o-mini")
    agency = _Agency(agent)

    apply_openai_client_config(
        agency,
        ClientConfig(api_key="sk-openai", base_url="https://chatgpt.com/backend-api/codex"),
    )

    assert isinstance(agent.model, OpenAIResponsesModel)
    assert agent.model_settings is not None
    assert agent.model_settings.store is False
    assert agent.model_settings.truncation is None


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


def test_model_override_applies_to_all_agents() -> None:
    """client_config.model should replace every agent's model for the request."""
    pytest.importorskip("agents")

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    a1 = Agent(name="A1", instructions="x", model="gpt-4o-mini")
    a2 = Agent(name="A2", instructions="y", model="gpt-4o")
    agency = type("Agency", (), {"agents": {"A1": a1, "A2": a2}})()

    apply_openai_client_config(agency, ClientConfig(model="gpt-4.1"))

    assert a1.model == "gpt-4.1"
    assert a2.model == "gpt-4.1"


def test_model_override_preserves_openai_responses_client() -> None:
    """config.model on an OpenAIResponsesModel agent keeps the embedded client + transport."""
    pytest.importorskip("agents")

    from agents import OpenAIResponsesModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    embedded = AsyncOpenAI(api_key="sk-agent", base_url="https://api.agent.test/v1")
    original = OpenAIResponsesModel(model="gpt-4o", openai_client=embedded)
    agent = Agent(name="A", instructions="x", model=original)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="gpt-4.1"))

    assert isinstance(agent.model, OpenAIResponsesModel)
    assert agent.model.model == "gpt-4.1"
    assert agent.model._client is embedded


def test_model_override_preserves_chat_completions_transport() -> None:
    """config.model on an OpenAIChatCompletionsModel agent keeps the ChatCompletions transport + client."""
    pytest.importorskip("agents")

    from agents import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    embedded = AsyncOpenAI(api_key="sk-agent", base_url="https://chat.agent.test/v1")
    original = OpenAIChatCompletionsModel(model="gpt-4o", openai_client=embedded)
    agent = Agent(name="A", instructions="x", model=original)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="gpt-4.1"))

    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    assert agent.model.model == "gpt-4.1"
    assert agent.model._client is embedded


def test_model_override_preserves_litellm_credentials() -> None:
    """config.model on a LitellmModel agent keeps the existing base_url + api_key."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    original = LitellmModel(model="anthropic/claude-sonnet-4", base_url="http://litellm.local", api_key="sk-existing")
    agent = Agent(name="A", instructions="x", model=original)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="litellm/anthropic/claude-opus-4"))

    assert isinstance(agent.model, LitellmModel)
    assert agent.model.model == "anthropic/claude-opus-4"
    assert agent.model.base_url == "http://litellm.local"
    assert agent.model.api_key == "sk-existing"


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


def test_provider_path_model_override_routes_request_gateway_client() -> None:
    """Provider-prefixed request model must still flow through the request gateway client."""
    pytest.importorskip("agents")

    from agents import OpenAIResponsesModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    embedded = AsyncOpenAI(api_key="sk-agent", base_url="https://api.agent.test/v1")
    agent = Agent(name="A", instructions="x", model=OpenAIResponsesModel(model="gpt-4o", openai_client=embedded))
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="anthropic/claude-sonnet-4",
            base_url="https://gateway.test/v1",
            api_key="sk-gateway",
        ),
    )

    assert isinstance(agent.model, OpenAIResponsesModel)
    assert agent.model.model == "anthropic/claude-sonnet-4"
    # The embedded client must be replaced by the request-scoped gateway client.
    assert agent.model._client is not embedded
    assert agent.model._client.api_key == "sk-gateway"
    assert str(agent.model._client.base_url).startswith("https://gateway.test")


def test_model_override_refreshes_gpt5_framework_defaults() -> None:
    """Swapping to a GPT-5 model should re-layer reasoning defaults without wiping headers."""
    pytest.importorskip("agents")

    from agents import ModelSettings

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model="gpt-4o-mini")
    agent.model_settings = ModelSettings(extra_headers={"x-caller": "1"})
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="gpt-5"))

    # Reasoning effort from the SDK GPT-5 defaults must reach the agent after the swap.
    assert agent.model == "gpt-5"
    assert agent.model_settings is not None
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "low"
    # Caller-set extra_headers must survive the refresh.
    assert agent.model_settings.extra_headers == {"x-caller": "1"}


def test_model_override_preserves_openclaw_usage_alias() -> None:
    """OpenClaw usage-name alias must survive a request model swap."""
    pytest.importorskip("agents")

    from agents import OpenAIResponsesModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.model_utils import get_usage_tracking_model_name

    embedded = AsyncOpenAI(api_key="sk-agent", base_url="https://openclaw.test/v1")
    source = OpenAIResponsesModel(model="openclaw:main", openai_client=embedded)
    source._agency_swarm_usage_model_name = "openai/gpt-5.4"  # type: ignore[attr-defined]
    agent = Agent(name="A", instructions="x", model=source)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="openclaw:main"))

    assert isinstance(agent.model, OpenAIResponsesModel)
    # Same name, new instance — the custom alias must carry over.
    assert get_usage_tracking_model_name(agent.model) == "openai/gpt-5.4"


def test_string_model_override_wraps_gateway_for_provider_prefix() -> None:
    """Bare-string agents whose request model is provider-prefixed must still bind the gateway client."""
    pytest.importorskip("agents")

    from agents import OpenAIResponsesModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model="gpt-4o")
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="anthropic/claude-sonnet-4",
            base_url="https://gateway.test/v1",
            api_key="sk-gateway",
        ),
    )

    # The provider-prefixed name must route through the request-scoped gateway client,
    # not silently stay as a bare string (which would skip the override entirely).
    assert isinstance(agent.model, OpenAIResponsesModel)
    assert agent.model.model == "anthropic/claude-sonnet-4"
    assert agent.model._client.api_key == "sk-gateway"
    assert str(agent.model._client.base_url).startswith("https://gateway.test")


def test_model_override_does_not_stick_old_gpt5_reasoning_settings() -> None:
    """Swapping GPT-5 -> GPT-4o must recompute settings, not inherit GPT-5 reasoning."""
    pytest.importorskip("agents")

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    # Agent starts on gpt-5, which layers reasoning.effort="low" at construction.
    agent = Agent(name="A", instructions="x", model="gpt-5")
    assert agent.model_settings is not None
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "low"

    agency = type("Agency", (), {"agents": {"A": agent}})()
    apply_openai_client_config(agency, ClientConfig(model="gpt-4o"))

    # After swapping to gpt-4o, the old GPT-5 reasoning defaults must not stick.
    assert agent.model == "gpt-4o"
    assert agent.model_settings is not None
    assert agent.model_settings.reasoning is None


def test_model_override_carries_openclaw_default_settings_alias() -> None:
    """OpenClaw default-settings alias must survive a same-name request model swap."""
    pytest.importorskip("agents")

    from agents import OpenAIResponsesModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.model_utils import get_default_settings_model_name

    embedded = AsyncOpenAI(api_key="sk-agent", base_url="https://openclaw.test/v1")
    source = OpenAIResponsesModel(model="openclaw:main", openai_client=embedded)
    source._agency_swarm_default_model_name = "gpt-5"  # type: ignore[attr-defined]
    agent = Agent(name="A", instructions="x", model=source)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="openclaw:main"))

    assert isinstance(agent.model, OpenAIResponsesModel)
    # OpenClaw default-settings lookup relies on this alias being carried.
    assert get_default_settings_model_name(agent.model) == "gpt-5"


def test_model_override_drops_usage_alias_when_model_name_changes() -> None:
    """OpenClaw usage alias must NOT be copied when the swap changes the model name."""
    pytest.importorskip("agents")

    from agents import OpenAIResponsesModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.model_utils import get_usage_tracking_model_name

    embedded = AsyncOpenAI(api_key="sk-agent", base_url="https://openclaw.test/v1")
    source = OpenAIResponsesModel(model="openclaw:main", openai_client=embedded)
    source._agency_swarm_usage_model_name = "openai/gpt-5.4"  # type: ignore[attr-defined]
    agent = Agent(name="A", instructions="x", model=source)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="gpt-4.1"))

    assert isinstance(agent.model, OpenAIResponsesModel)
    assert agent.model.model == "gpt-4.1"
    # The alias belonged to openclaw:main — it must not inherit onto gpt-4.1.
    assert get_usage_tracking_model_name(agent.model) == "gpt-4.1"

"""Minimal tests for FastAPI request models that include `client_config`.

The end-to-end behavior is covered in integration tests under `tests/integration/fastapi/`.
"""

import pytest

from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig


class TestClientConfig:
    """Tests for ClientConfig model."""

    def test_config_with_all_fields(self) -> None:
        """Config accepts both base_url and api_key."""
        config = ClientConfig(
            base_url="https://custom.api.com",
            api_key="sk-custom-key",
        )
        assert config.base_url == "https://custom.api.com"
        assert config.api_key == "sk-custom-key"

    def test_config_with_only_base_url(self) -> None:
        """Config can specify only base_url."""
        config = ClientConfig(base_url="https://custom.api.com")
        assert config.base_url == "https://custom.api.com"
        assert config.api_key is None

    def test_config_with_only_api_key(self) -> None:
        """Config can specify only api_key."""
        config = ClientConfig(api_key="sk-custom-key")
        assert config.base_url is None
        assert config.api_key == "sk-custom-key"

    def test_config_empty(self) -> None:
        """Config can be created with no overrides."""
        config = ClientConfig()
        assert config.base_url is None
        assert config.api_key is None
        assert config.default_headers is None
        assert config.litellm_keys is None

    def test_config_with_litellm_keys(self) -> None:
        """Config accepts litellm_keys for provider-specific API keys."""
        config = ClientConfig(
            litellm_keys={
                "anthropic": "sk-ant-xxx",
                "gemini": "AIza...",
            }
        )
        assert config.litellm_keys is not None
        assert config.litellm_keys["anthropic"] == "sk-ant-xxx"
        assert config.litellm_keys["gemini"] == "AIza..."


class TestBaseRequestWithClientConfig:
    """Tests for BaseRequest including client_config."""

    def test_request_without_client_config(self) -> None:
        """Request works without client config."""
        request = BaseRequest(message="Hello")
        assert request.client_config is None

    def test_request_with_client_config(self) -> None:
        """Request accepts client config."""
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

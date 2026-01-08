"""Unit tests for OpenAI client configuration in FastAPI endpoints."""

import pytest
from agents import OpenAIChatCompletionsModel, OpenAIResponsesModel
from openai import AsyncOpenAI

from agency_swarm import Agency, Agent
from agency_swarm.integrations.fastapi_utils.endpoint_handlers import (
    _apply_client_to_agent,
    _get_litellm_provider,
    _is_litellm_model,
    apply_openai_client_config,
)
from agency_swarm.integrations.fastapi_utils.request_models import (
    BaseRequest,
    OpenAIClientConfig,
)


class TestOpenAIClientConfig:
    """Tests for OpenAIClientConfig model."""

    def test_config_with_all_fields(self) -> None:
        """Config accepts both base_url and api_key."""
        config = OpenAIClientConfig(
            base_url="https://custom.api.com",
            api_key="sk-custom-key",
        )
        assert config.base_url == "https://custom.api.com"
        assert config.api_key == "sk-custom-key"

    def test_config_with_only_base_url(self) -> None:
        """Config can specify only base_url."""
        config = OpenAIClientConfig(base_url="https://custom.api.com")
        assert config.base_url == "https://custom.api.com"
        assert config.api_key is None

    def test_config_with_only_api_key(self) -> None:
        """Config can specify only api_key."""
        config = OpenAIClientConfig(api_key="sk-custom-key")
        assert config.base_url is None
        assert config.api_key == "sk-custom-key"

    def test_config_empty(self) -> None:
        """Config can be created with no overrides."""
        config = OpenAIClientConfig()
        assert config.base_url is None
        assert config.api_key is None
        assert config.litellm_keys is None

    def test_config_with_litellm_keys(self) -> None:
        """Config accepts litellm_keys for provider-specific API keys."""
        config = OpenAIClientConfig(
            litellm_keys={
                "anthropic": "sk-ant-xxx",
                "gemini": "AIza...",
            }
        )
        assert config.litellm_keys is not None
        assert config.litellm_keys["anthropic"] == "sk-ant-xxx"
        assert config.litellm_keys["gemini"] == "AIza..."


class TestBaseRequestWithClientConfig:
    """Tests for BaseRequest including openai_client_config."""

    def test_request_without_client_config(self) -> None:
        """Request works without client config."""
        request = BaseRequest(message="Hello")
        assert request.openai_client_config is None

    def test_request_with_client_config(self) -> None:
        """Request accepts client config."""
        request = BaseRequest(
            message="Hello",
            openai_client_config=OpenAIClientConfig(
                base_url="https://custom.api.com",
                api_key="sk-custom-key",
            ),
        )
        assert request.openai_client_config is not None
        assert request.openai_client_config.base_url == "https://custom.api.com"
        assert request.openai_client_config.api_key == "sk-custom-key"


class TestApplyClientToAgent:
    """Tests for _apply_client_to_agent function."""

    def test_apply_to_string_model(self) -> None:
        """String model gets wrapped in OpenAIResponsesModel with custom client."""
        agent = Agent(name="TestAgent", instructions="Test", model="gpt-4o")
        custom_client = AsyncOpenAI(api_key="test-key", base_url="https://test.api.com")
        config = OpenAIClientConfig(api_key="test-key", base_url="https://test.api.com")

        _apply_client_to_agent(agent, custom_client, config)

        assert isinstance(agent.model, OpenAIResponsesModel)
        assert agent.model.model == "gpt-4o"

    def test_apply_to_responses_model(self) -> None:
        """OpenAIResponsesModel gets recreated with custom client."""
        original_client = AsyncOpenAI(api_key="original-key")
        agent = Agent(
            name="TestAgent",
            instructions="Test",
            model=OpenAIResponsesModel(model="gpt-4o", openai_client=original_client),
        )
        custom_client = AsyncOpenAI(api_key="test-key", base_url="https://test.api.com")
        config = OpenAIClientConfig(api_key="test-key", base_url="https://test.api.com")

        _apply_client_to_agent(agent, custom_client, config)

        assert isinstance(agent.model, OpenAIResponsesModel)
        assert agent.model.model == "gpt-4o"

    def test_apply_to_chat_completions_model(self) -> None:
        """OpenAIChatCompletionsModel gets recreated with custom client."""
        original_client = AsyncOpenAI(api_key="original-key")
        agent = Agent(
            name="TestAgent",
            instructions="Test",
            model=OpenAIChatCompletionsModel(model="gpt-4o", openai_client=original_client),
        )
        custom_client = AsyncOpenAI(api_key="test-key", base_url="https://test.api.com")
        config = OpenAIClientConfig(api_key="test-key", base_url="https://test.api.com")

        _apply_client_to_agent(agent, custom_client, config)

        assert isinstance(agent.model, OpenAIChatCompletionsModel)
        assert agent.model.model == "gpt-4o"


class TestApplyOpenAIClientConfig:
    """Tests for apply_openai_client_config function."""

    def test_apply_to_agency_with_single_agent(self) -> None:
        """Config is applied to single-agent agency."""
        agent = Agent(name="TestAgent", instructions="Test", model="gpt-4o")
        agency = Agency(agent)
        config = OpenAIClientConfig(
            base_url="https://custom.api.com",
            api_key="sk-custom-key",
        )

        apply_openai_client_config(agency, config)

        assert isinstance(agency.agents["TestAgent"].model, OpenAIResponsesModel)
        assert agency.agents["TestAgent"].model.model == "gpt-4o"

    def test_apply_to_agency_with_multiple_agents(self) -> None:
        """Config is applied to all agents in a multi-agent agency."""
        agent1 = Agent(name="Agent1", instructions="Test1", model="gpt-4o")
        agent2 = Agent(name="Agent2", instructions="Test2", model="gpt-4o-mini")
        agency = Agency(agent1, agent2, communication_flows=[agent1 > agent2])
        config = OpenAIClientConfig(
            base_url="https://custom.api.com",
            api_key="sk-custom-key",
        )

        apply_openai_client_config(agency, config)

        assert isinstance(agency.agents["Agent1"].model, OpenAIResponsesModel)
        assert agency.agents["Agent1"].model.model == "gpt-4o"
        assert isinstance(agency.agents["Agent2"].model, OpenAIResponsesModel)
        assert agency.agents["Agent2"].model.model == "gpt-4o-mini"

    def test_no_op_with_empty_config(self) -> None:
        """Empty config does not modify agents."""
        agent = Agent(name="TestAgent", instructions="Test", model="gpt-4o")
        original_model = agent.model
        agency = Agency(agent)
        config = OpenAIClientConfig()  # Both None

        apply_openai_client_config(agency, config)

        # Model should remain unchanged (string)
        assert agency.agents["TestAgent"].model == original_model
        assert isinstance(agency.agents["TestAgent"].model, str)

    def test_apply_with_only_api_key(self) -> None:
        """Config with only api_key still creates new client."""
        agent = Agent(name="TestAgent", instructions="Test", model="gpt-4o")
        agency = Agency(agent)
        config = OpenAIClientConfig(api_key="sk-custom-key")

        apply_openai_client_config(agency, config)

        assert isinstance(agency.agents["TestAgent"].model, OpenAIResponsesModel)

    def test_apply_with_only_base_url(self) -> None:
        """Config with only base_url still creates new client."""
        agent = Agent(name="TestAgent", instructions="Test", model="gpt-4o")
        agency = Agency(agent)
        config = OpenAIClientConfig(base_url="https://custom.api.com")

        apply_openai_client_config(agency, config)

        assert isinstance(agency.agents["TestAgent"].model, OpenAIResponsesModel)


class TestLiteLLMModelDetection:
    """Tests for LiteLLM model detection and skipping."""

    def test_is_litellm_model_with_litellm_prefix(self) -> None:
        """Models with litellm/ prefix are detected as LiteLLM."""
        assert _is_litellm_model("litellm/anthropic/claude-sonnet-4-20250514") is True
        assert _is_litellm_model("litellm/gemini/gemini-2.5-pro") is True

    def test_is_litellm_model_with_openai_model(self) -> None:
        """Standard OpenAI models are not detected as LiteLLM."""
        assert _is_litellm_model("gpt-4o") is False
        assert _is_litellm_model("gpt-4o-mini") is False

    def test_apply_handles_litellm_string_model_without_litellm_installed(self) -> None:
        """LiteLLM string models remain unchanged when litellm is not installed."""
        agent = Agent(
            name="TestAgent",
            instructions="Test",
            model="litellm/anthropic/claude-sonnet-4-20250514",
        )
        original_model = agent.model
        custom_client = AsyncOpenAI(api_key="test-key", base_url="https://test.api.com")
        config = OpenAIClientConfig(api_key="test-key", base_url="https://test.api.com")

        # When litellm is not installed, model remains unchanged (with warning logged)
        _apply_client_to_agent(agent, custom_client, config)

        # Model should remain unchanged (string) when litellm not available
        # If litellm IS installed, this would become a LitellmModel instance
        assert agent.model == original_model or hasattr(agent.model, "model")

    def test_apply_skips_litellm_in_mixed_agency(self) -> None:
        """In mixed agency, only OpenAI models get custom client."""
        openai_agent = Agent(name="OpenAIAgent", instructions="Test", model="gpt-4o")
        litellm_agent = Agent(
            name="LiteLLMAgent",
            instructions="Test",
            model="litellm/anthropic/claude-sonnet-4-20250514",
        )
        agency = Agency(
            openai_agent,
            litellm_agent,
            communication_flows=[openai_agent > litellm_agent],
        )
        config = OpenAIClientConfig(
            base_url="https://custom.api.com",
            api_key="sk-custom-key",
        )

        apply_openai_client_config(agency, config)

        # OpenAI agent should be modified
        assert isinstance(agency.agents["OpenAIAgent"].model, OpenAIResponsesModel)
        assert agency.agents["OpenAIAgent"].model.model == "gpt-4o"

        # LiteLLM agent: unchanged if litellm not installed, or LitellmModel if installed
        litellm_model = agency.agents["LiteLLMAgent"].model
        assert isinstance(litellm_model, str) or hasattr(litellm_model, "model")


class TestLiteLLMProviderExtraction:
    """Tests for _get_litellm_provider function."""

    def test_extract_provider_from_full_litellm_path(self) -> None:
        """Provider is extracted from litellm/provider/model format."""
        assert _get_litellm_provider("litellm/anthropic/claude-sonnet-4") == "anthropic"
        assert _get_litellm_provider("litellm/gemini/gemini-2.5-pro") == "gemini"
        assert _get_litellm_provider("litellm/azure/gpt-4") == "azure"

    def test_extract_provider_without_litellm_prefix(self) -> None:
        """Provider is extracted from provider/model format."""
        assert _get_litellm_provider("anthropic/claude-sonnet-4") == "anthropic"
        assert _get_litellm_provider("gemini/gemini-2.5-pro") == "gemini"

    def test_no_provider_for_simple_model_name(self) -> None:
        """Returns None for model names without provider prefix."""
        assert _get_litellm_provider("claude-sonnet-4") is None
        assert _get_litellm_provider("gpt-4o") is None


class TestLiteLLMKeysConfig:
    """Tests for litellm_keys provider-specific API key configuration."""

    def test_litellm_keys_in_config(self) -> None:
        """Config accepts litellm_keys for mixed provider setups."""
        config = OpenAIClientConfig(
            base_url="https://proxy.example.com",
            litellm_keys={
                "anthropic": "sk-ant-xxx",
                "gemini": "AIza...",
            },
        )
        assert config.litellm_keys is not None
        assert len(config.litellm_keys) == 2
        assert config.litellm_keys["anthropic"] == "sk-ant-xxx"
        assert config.litellm_keys["gemini"] == "AIza..."

    def test_litellm_keys_raises_error_without_litellm(self, monkeypatch) -> None:
        """Raises error if litellm_keys provided but litellm not installed."""
        import agency_swarm.integrations.fastapi_utils.request_models as req_models

        # Mock litellm not being installed
        monkeypatch.setattr(req_models, "_LITELLM_INSTALLED", False)

        with pytest.raises(ValueError, match="litellm_keys requires litellm to be installed"):
            OpenAIClientConfig(
                litellm_keys={"anthropic": "sk-ant-xxx"},
            )

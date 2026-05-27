from types import SimpleNamespace

import pytest


class FakeLitellmModel:
    def __init__(self, model: str, base_url: str | None = None, api_key: str | None = None) -> None:
        self.model = model
        self.base_url = base_url
        self.api_key = api_key


def _patch_fake_litellm(monkeypatch: pytest.MonkeyPatch) -> None:
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers

    monkeypatch.setattr(endpoint_handlers, "_LITELLM_AVAILABLE", True)
    monkeypatch.setattr(endpoint_handlers, "LitellmModel", FakeLitellmModel)


def _fake_agency(model: object) -> SimpleNamespace:
    from agents.model_settings import ModelSettings

    agent = SimpleNamespace(name="A", model=model, model_settings=ModelSettings())
    return SimpleNamespace(agents={"A": agent})


def test_litellm_agent_can_override_to_openai_model_with_request_credentials() -> None:
    """A LiteLLM agent can switch to an OpenAI model when request credentials are supplied."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents import OpenAIResponsesModel
    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    original = LitellmModel(model="anthropic/claude-sonnet-4", base_url="http://litellm.local", api_key="sk-existing")
    agent = Agent(name="A", instructions="x", model=original)
    agency = SimpleNamespace(agents={"A": agent})

    apply_openai_client_config(agency, ClientConfig(model="gpt-4.1", api_key="sk-request-openai"))

    assert isinstance(agent.model, OpenAIResponsesModel)
    assert agent.model.model == "gpt-4.1"
    assert agent.model._client.api_key == "sk-request-openai"


def test_litellm_agent_override_to_openai_model_without_litellm_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    """The OpenAI override branch is covered even when the optional litellm package is absent."""
    pytest.importorskip("agents")

    from agents import OpenAIResponsesModel

    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    _patch_fake_litellm(monkeypatch)
    agency = _fake_agency(
        FakeLitellmModel(model="anthropic/claude-sonnet-4", base_url="http://litellm.local", api_key="sk-existing")
    )

    apply_openai_client_config(agency, ClientConfig(model="gpt-4.1", api_key="sk-request-openai"))

    agent = agency.agents["A"]
    assert isinstance(agent.model, OpenAIResponsesModel)
    assert agent.model.model == "gpt-4.1"
    assert agent.model._client.api_key == "sk-request-openai"


def test_litellm_agent_provider_override_keeps_litellm_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider-prefixed overrides on LiteLLM agents must stay on LitellmModel."""
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    _patch_fake_litellm(monkeypatch)
    agency = _fake_agency(
        FakeLitellmModel(model="anthropic/claude-sonnet-4", base_url="http://litellm.local", api_key="sk-existing")
    )
    config = ClientConfig(model="gemini/gemini-2.5-flash", api_key="sk-openai-present")
    config.litellm_keys = {"gemini": "sk-gemini"}

    apply_openai_client_config(agency, config)

    model = agency.agents["A"].model
    assert isinstance(model, FakeLitellmModel)
    assert model.model == "gemini/gemini-2.5-flash"
    assert model.base_url == "http://litellm.local"
    assert model.api_key == "sk-gemini"


def test_litellm_agent_openai_prefixed_override_strips_provider_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAI wrapper overrides must not send literal openai/... names to OpenAI."""
    pytest.importorskip("agents")

    from agents import OpenAIResponsesModel

    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    _patch_fake_litellm(monkeypatch)
    agency = _fake_agency(FakeLitellmModel(model="anthropic/claude-sonnet-4"))

    apply_openai_client_config(agency, ClientConfig(model="openai/gpt-4.1", api_key="sk-request-openai"))

    model = agency.agents["A"].model
    assert isinstance(model, OpenAIResponsesModel)
    assert model.model == "gpt-4.1"

"""Focused OpenRouter client override regressions."""

import pytest


def test_model_only_openrouter_override_requires_openrouter_key_with_official_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An injected OpenAI key must not become an OpenRouter credential."""
    pytest.importorskip("agents")

    from agents import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = AsyncOpenAI(
        api_key="sk-source-openai",
        base_url="https://api.openai.com/v1",
        default_headers={"x-source": "kept"},
        timeout=12,
        max_retries=3,
    )
    source = OpenAIChatCompletionsModel(model="gpt-4o-mini", openai_client=client)
    agent = Agent(name="A", instructions="x", model=source)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY is required"):
        apply_openai_client_config(agency, ClientConfig(model="openrouter/anthropic/claude-sonnet-4.5"))


def test_model_only_openrouter_override_does_not_reuse_custom_gateway_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model-only OpenRouter swap must route through the OpenRouter endpoint."""
    pytest.importorskip("agents")

    from agents import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.openrouter import get_openrouter_model_name

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter-env")
    client = AsyncOpenAI(
        api_key="sk-gateway",
        base_url="https://gateway.test/v1",
        default_headers={"x-source": "gateway"},
    )
    source = OpenAIChatCompletionsModel(model="gpt-4o-mini", openai_client=client)
    agent = Agent(name="A", instructions="x", model=source)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="openrouter/anthropic/claude-sonnet-4.5"))

    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    assert get_openrouter_model_name(agent.model) == "openrouter/anthropic/claude-sonnet-4.5"
    assert agent.model._client is not client
    assert agent.model._client.api_key == "sk-openrouter-env"
    assert str(agent.model._client.base_url).startswith("https://openrouter.ai/api/v1")

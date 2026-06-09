"""Focused OpenRouter client override regressions."""

import pytest


def test_model_only_openrouter_override_copies_custom_official_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """A model-only OpenRouter swap should keep a source key when no OpenRouter env key exists."""
    pytest.importorskip("agents")

    from agents import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.openrouter import get_openrouter_model_name

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = AsyncOpenAI(
        api_key="sk-source-openrouter",
        base_url="https://api.openai.com/v1",
        default_headers={"x-source": "kept"},
        timeout=12,
        max_retries=3,
    )
    source = OpenAIChatCompletionsModel(model="gpt-4o-mini", openai_client=client)
    agent = Agent(name="A", instructions="x", model=source)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="openrouter/anthropic/claude-sonnet-4.5"))

    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    assert agent.model.model == "anthropic/claude-sonnet-4.5"
    assert get_openrouter_model_name(agent.model) == "openrouter/anthropic/claude-sonnet-4.5"
    assert agent.model._client is not client
    assert agent.model._client.api_key == "sk-source-openrouter"
    assert str(agent.model._client.base_url).startswith("https://openrouter.ai/api/v1")
    assert agent.model._client.timeout == 12
    assert agent.model._client.max_retries == 3
    assert dict(agent.model._client.default_headers)["x-source"] == "kept"

"""OrcaRouter model integration tests."""

import pytest

from agency_swarm import Agent


def test_agent_initialization_orcarouter_model_uses_orcarouter_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Direct orcarouter/... Agent models should route through OrcaRouter."""
    from agents import OpenAIChatCompletionsModel

    from agency_swarm.utils.orcarouter import get_orcarouter_model_name

    monkeypatch.setenv("ORCAROUTER_API_KEY", "sk-orca-test")

    agent = Agent(name="OrcaRouterAgent", instructions="Test", model="orcarouter/openai/gpt-5.5")

    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    assert agent.model.model == "openai/gpt-5.5"
    assert get_orcarouter_model_name(agent.model) == "orcarouter/openai/gpt-5.5"
    assert agent.model._client.api_key == "sk-orca-test"
    assert str(agent.model._client.base_url).startswith("https://api.orcarouter.ai/v1")


def test_agent_initialization_orcarouter_model_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Direct orcarouter/... Agent models should fail before making provider calls when no key is available."""
    monkeypatch.delenv("ORCAROUTER_API_KEY", raising=False)

    with pytest.raises(ValueError, match="ORCAROUTER_API_KEY is required"):
        Agent(name="OrcaRouterAgent", instructions="Test", model="orcarouter/openai/gpt-5.5")


def test_agent_initialization_orcarouter_model_skips_client_in_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dry-run metadata setup should not require or build an OrcaRouter client."""
    from agency_swarm.agent import initialization
    from agency_swarm.utils.dry_run import force_dry_run

    monkeypatch.delenv("ORCAROUTER_API_KEY", raising=False)

    def _fail_build(*_args, **_kwargs):
        raise AssertionError("dry-run must not build an OrcaRouter client")

    monkeypatch.setattr(initialization, "build_orcarouter_chat_model", _fail_build)

    with force_dry_run():
        agent = Agent(name="OrcaRouterAgent", instructions="Test", model="orcarouter/openai/gpt-5.5")

    assert agent.model == "orcarouter/openai/gpt-5.5"


def test_build_orcarouter_chat_model_strips_prefix_and_sets_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    """build_orcarouter_chat_model strips the prefix and records gateway aliases."""
    monkeypatch.setenv("ORCAROUTER_API_KEY", "sk-orca-test")

    from agency_swarm.utils.orcarouter import (
        get_orcarouter_model_name,
        is_orcarouter_model,
        is_orcarouter_model_name,
        strip_orcarouter_prefix,
    )

    assert is_orcarouter_model_name("orcarouter/openai/gpt-5.5")
    assert not is_orcarouter_model_name("openrouter/anthropic/claude-sonnet-4.5")
    assert strip_orcarouter_prefix("orcarouter/openai/gpt-5.5") == "openai/gpt-5.5"

    model = Agent(name="OrcaRouterAgent", instructions="Test", model="orcarouter/anthropic/claude-sonnet-5").model
    assert is_orcarouter_model(model)
    assert get_orcarouter_model_name(model) == "orcarouter/anthropic/claude-sonnet-5"


def test_orcarouter_model_usage_and_default_settings_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """Usage tracking keeps the gateway alias while SDK default settings use the stripped name."""
    monkeypatch.setenv("ORCAROUTER_API_KEY", "sk-orca-test")

    from agency_swarm.utils.model_utils import get_default_settings_model_name, get_usage_tracking_model_name

    model = Agent(name="OrcaRouterAgent", instructions="Test", model="orcarouter/openai/gpt-5.5").model
    assert get_usage_tracking_model_name(model) == "orcarouter/openai/gpt-5.5"
    assert get_default_settings_model_name(model) == "gpt-5.5"


def test_visualization_describe_model_shows_orcarouter_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    """Visualization should surface the full orcarouter/... alias for wrapped models."""
    monkeypatch.setenv("ORCAROUTER_API_KEY", "sk-orca-test")

    from agency_swarm.agency.visualization import _describe_model

    model = Agent(name="OrcaRouterAgent", instructions="Test", model="orcarouter/openai/gpt-5.5").model
    assert _describe_model(model) == "orcarouter/openai/gpt-5.5"

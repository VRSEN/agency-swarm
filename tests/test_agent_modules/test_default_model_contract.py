import pytest
from agents import ModelSettings
from openai.types.shared.reasoning import Reasoning

from agency_swarm import Agent
from agency_swarm.agent.constants import FRAMEWORK_DEFAULT_MODEL
from agency_swarm.utils.usage_tracking import calculate_openai_cost, get_model_pricing, load_pricing_data
from tests.deterministic_model import DeterministicModel


class _NamelessModel(DeterministicModel):
    def __init__(self) -> None:
        pass


def test_model_settings_defaults_distinguish_nameless_model_objects_from_luna() -> None:
    custom_model_agent = Agent(name="CustomModel", instructions="Test", model=_NamelessModel())
    assert custom_model_agent.model_settings.reasoning is None
    assert custom_model_agent.model_settings.verbosity is None

    default_agent = Agent(name="DefaultModel", instructions="Test")
    explicit_luna_agent = Agent(name="ExplicitLuna", instructions="Test", model="gpt-5.6-luna")
    none_model_agent = Agent(name="NoneModel", instructions="Test", model=None)

    for agent in (default_agent, explicit_luna_agent, none_model_agent):
        assert agent.model_settings.reasoning is not None
        assert agent.model_settings.reasoning.effort == "none"

    assert default_agent.model == FRAMEWORK_DEFAULT_MODEL
    assert explicit_luna_agent.model == "gpt-5.6-luna"
    assert none_model_agent.model == FRAMEWORK_DEFAULT_MODEL


def test_framework_default_model_normalizes_none_without_overriding_explicit_configuration() -> None:
    default_agent = Agent(name="DefaultAgent", instructions="Test", model=None)
    assert default_agent.model == FRAMEWORK_DEFAULT_MODEL
    assert default_agent.model_settings.reasoning == Reasoning(effort="none")

    explicit_model_agent = Agent(name="ExplicitModelAgent", instructions="Test", model="gpt-4.1")
    assert explicit_model_agent.model == "gpt-4.1"

    explicit_reasoning = Reasoning(effort="high")
    configured_agent = Agent(
        name="ConfiguredAgent",
        instructions="Test",
        model=None,
        model_settings=ModelSettings(reasoning=explicit_reasoning),
    )
    assert configured_agent.model == FRAMEWORK_DEFAULT_MODEL
    assert configured_agent.model_settings.reasoning == explicit_reasoning


def test_framework_default_model_has_bundled_pricing() -> None:
    pricing_data = load_pricing_data()

    assert get_model_pricing(FRAMEWORK_DEFAULT_MODEL, pricing_data) is not None
    assert calculate_openai_cost(FRAMEWORK_DEFAULT_MODEL, 1000, 1000, pricing_data=pricing_data) > 0.0


def test_framework_default_model_uses_bundled_long_context_pricing() -> None:
    pricing_data = load_pricing_data()
    pricing = get_model_pricing(FRAMEWORK_DEFAULT_MODEL, pricing_data)
    assert pricing is not None
    assert pricing["cache_creation_input_token_cost_above_272k_tokens"] == 2.5e-6
    assert pricing["cache_read_input_token_cost_above_272k_tokens"] == 2e-7
    assert pricing["input_cost_per_token_above_272k_tokens"] == 2e-6
    assert pricing["output_cost_per_token_above_272k_tokens"] == 9e-6

    expected_cost = 300_000 * pricing["input_cost_per_token_above_272k_tokens"]
    expected_cost += 1_000 * pricing["output_cost_per_token_above_272k_tokens"]
    assert expected_cost == pytest.approx(0.609)
    assert calculate_openai_cost(
        FRAMEWORK_DEFAULT_MODEL,
        input_tokens=300_000,
        output_tokens=1_000,
        pricing_data=pricing_data,
    ) == pytest.approx(expected_cost)

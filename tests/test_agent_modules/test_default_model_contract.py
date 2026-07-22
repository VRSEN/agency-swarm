from agents import ModelSettings
from openai.types.shared.reasoning import Reasoning

from agency_swarm import Agent
from agency_swarm.agent.constants import FRAMEWORK_DEFAULT_MODEL
from agency_swarm.utils.usage_tracking import calculate_openai_cost, get_model_pricing, load_pricing_data


def test_framework_default_model_disables_reasoning_without_overriding_explicit_setting() -> None:
    default_agent = Agent(name="DefaultAgent", instructions="Test")
    assert default_agent.model == FRAMEWORK_DEFAULT_MODEL
    assert default_agent.model_settings.reasoning == Reasoning(effort="none")

    explicit_reasoning = Reasoning(effort="high")
    configured_agent = Agent(
        name="ConfiguredAgent",
        instructions="Test",
        model_settings=ModelSettings(reasoning=explicit_reasoning),
    )
    assert configured_agent.model_settings.reasoning == explicit_reasoning


def test_framework_default_model_has_bundled_pricing() -> None:
    pricing_data = load_pricing_data()

    assert get_model_pricing(FRAMEWORK_DEFAULT_MODEL, pricing_data) is not None
    assert calculate_openai_cost(FRAMEWORK_DEFAULT_MODEL, 1000, 1000, pricing_data=pricing_data) > 0.0

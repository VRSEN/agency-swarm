import pytest

from agency_swarm import Agency, Agent
from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig


@pytest.mark.parametrize("bad_summary", [{"summary": "auto"}, ["auto"]])
def test_non_str_reasoning_summary_survives_request_overrides(bad_summary: object) -> None:
    agent = Agent(name="Assistant", model="gpt-5")
    agency = Agency(agent)
    prior_reasoning = agent.model_settings.reasoning

    apply_openai_client_config(agency, ClientConfig(model_settings_extra_args={"reasoning_summary": bad_summary}))

    assert agent.model_settings.reasoning == prior_reasoning
    assert agent.model_settings.extra_args == {"reasoning_summary": bad_summary}


def test_reasoning_dict_with_non_str_summary_keeps_effort() -> None:
    agent = Agent(name="Assistant", model="gpt-5")
    agency = Agency(agent)

    apply_openai_client_config(
        agency,
        ClientConfig(model_settings_extra_args={"reasoning": {"effort": "high", "summary": {"bad": "dict"}}}),
    )

    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "high"
    assert agent.model_settings.reasoning.summary is None


def test_extra_body_reasoning_with_non_str_summary_keeps_effort() -> None:
    agent = Agent(name="Assistant", model="gpt-5")
    agency = Agency(agent)

    apply_openai_client_config(
        agency,
        ClientConfig(model_settings_extra_args={"extra_body": {"reasoning": {"effort": "low", "summary": ["bad"]}}}),
    )

    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "low"
    assert agent.model_settings.reasoning.summary is None


def test_str_reasoning_summary_still_applies() -> None:
    agent = Agent(name="Assistant", model="gpt-5")
    agency = Agency(agent)

    apply_openai_client_config(agency, ClientConfig(model_settings_extra_args={"reasoning_summary": "detailed"}))

    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.summary == "detailed"
    assert agent.model_settings.extra_args is None

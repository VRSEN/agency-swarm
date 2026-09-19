import importlib

import pytest
from agents import ModelSettings

from agency_swarm import Agency, Agent
from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

pytest.importorskip("litellm")
LitellmModel = importlib.import_module("agents.extensions.models.litellm_model").LitellmModel


@pytest.mark.parametrize("configured_on_agent", [False, True])
def test_structured_reasoning_effort_survives_request_overrides(configured_on_agent: bool) -> None:
    reasoning_effort = {"effort": "high", "summary": "auto"}
    agent = Agent(
        name="Assistant",
        model=LitellmModel(model="openai/gpt-5"),
        model_settings=ModelSettings(
            extra_args={"reasoning_effort": reasoning_effort} if configured_on_agent else None,
        ),
    )
    agency = Agency(agent)
    extra_args: dict[str, object] = {"max_tokens": 128}
    if not configured_on_agent:
        extra_args["reasoning_effort"] = reasoning_effort

    apply_openai_client_config(agency, ClientConfig(model_settings_extra_args=extra_args))

    assert agent.model_settings.max_tokens == 128
    assert agent.model_settings.extra_args == {"reasoning_effort": reasoning_effort}


def test_normalized_reasoning_effort_survives_a_later_override() -> None:
    agent = Agent(name="Assistant", model=LitellmModel(model="openai/gpt-5"))
    agency = Agency(agent)
    apply_openai_client_config(
        agency,
        ClientConfig(model_settings_extra_args={"reasoning_effort": "high", "reasoning_summary": "auto"}),
    )

    apply_openai_client_config(agency, ClientConfig(model_settings_extra_args={"max_tokens": 128}))

    assert agent.model_settings.max_tokens == 128
    assert agent.model_settings.extra_args == {"reasoning_effort": {"effort": "high", "summary": "auto"}}

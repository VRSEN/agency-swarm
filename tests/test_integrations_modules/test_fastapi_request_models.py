"""Tests for FastAPI request models and validators."""

from __future__ import annotations

import pytest

from agency_swarm.integrations.fastapi_utils import request_models


def test_run_agent_input_custom_accepts_optional_fields() -> None:
    """Optional fields should hydrate without altering base fields."""
    payload = request_models.RunAgentInputCustom(
        thread_id="thread",
        run_id="run",
        state=None,
        messages=[],
        tools=[],
        context=[],
        forwarded_props=None,
        chat_history=[{"agent": "alpha"}],
        additional_instructions="extra",
    )

    assert payload.chat_history == [{"agent": "alpha"}]
    assert payload.additional_instructions == "extra"


def test_add_agent_validator_accepts_known_names() -> None:
    """Validator should pass through known agent names."""
    agents = {"alpha": object()}
    Validated = request_models.add_agent_validator(request_models.BaseRequest, agents)

    request = Validated(message="hello", recipient_agent="alpha")

    assert request.recipient_agent == "alpha"


def test_add_agent_validator_rejects_unknown_names() -> None:
    """Unknown agent names should raise a ValueError with available options."""
    agents = {"alpha": object()}
    Validated = request_models.add_agent_validator(request_models.BaseRequest, agents)

    with pytest.raises(ValueError) as exc_info:
        Validated(message="hello", recipient_agent="beta")

    assert "['alpha']" in str(exc_info.value)


def test_add_agent_validator_allows_missing_recipient() -> None:
    """recipient_agent should remain optional."""
    agents = {"alpha": object()}
    Validated = request_models.add_agent_validator(request_models.BaseRequest, agents)

    request = Validated(message="hello")

    assert request.recipient_agent is None

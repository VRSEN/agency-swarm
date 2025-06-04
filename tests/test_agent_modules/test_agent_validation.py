from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, ValidationError

from agency_swarm import Agent

# --- Validation Helper Functions ---


def validator_true(response_text: str) -> bool:
    return True


def validator_false(response_text: str) -> bool:
    return False


def validator_raises(response_text: str):
    raise ValueError("Validation error")


def validator_pydantic(response_text: str):
    class ResponseModel(BaseModel):
        key: str

    try:
        ResponseModel.model_validate_json(response_text)
        return True
    except ValidationError:
        return False


# --- Validation Tests ---


def test_validator_raises_exception(minimal_agent):
    """Test that validator exceptions are handled gracefully."""

    def failing_validator(response_text: str) -> bool:
        raise ValueError("Validator failed")

    agent = Agent(name="TestAgent", instructions="Test", response_validator=failing_validator)
    # The _validate_response method should handle exceptions gracefully
    result = agent._validate_response("test response")
    assert result is False  # Should return False when validator raises exception


def test_validate_response_none():
    """Test _validate_response with no validator."""
    agent = Agent(name="TestAgent", instructions="Test")
    assert agent._validate_response("any response") is True


def test_validate_response_true():
    """Test _validate_response with validator that returns True."""
    agent = Agent(name="TestAgent", instructions="Test", response_validator=validator_true)
    assert agent._validate_response("any response") is True


def test_validate_response_false():
    """Test _validate_response with validator that returns False."""
    agent = Agent(name="TestAgent", instructions="Test", response_validator=validator_false)
    assert agent._validate_response("any response") is False


def test_validate_response_raises():
    """Test _validate_response with validator that raises exception."""
    agent = Agent(name="TestAgent", instructions="Test", response_validator=validator_raises)
    assert agent._validate_response("any response") is False


def test_validate_response_pydantic_valid():
    """Test _validate_response with Pydantic validator and valid JSON."""
    agent = Agent(name="TestAgent", instructions="Test", response_validator=validator_pydantic)
    valid_json = '{"key": "value"}'
    assert agent._validate_response(valid_json) is True


def test_validate_response_pydantic_invalid():
    """Test _validate_response with Pydantic validator and invalid JSON."""
    agent = Agent(name="TestAgent", instructions="Test", response_validator=validator_pydantic)
    invalid_json = '{"wrong_key": "value"}'
    assert agent._validate_response(invalid_json) is False


@pytest.mark.asyncio
async def test_get_response_integrates_validation_pass(mock_thread_manager, mock_agency_instance):
    """Test that get_response integrates with response validation (passing case)."""
    # Use a real Agent instance with validation
    agent = Agent(name="TestAgent", instructions="Test", response_validator=validator_true)
    agent._set_agency_instance(mock_agency_instance)
    agent._set_thread_manager(mock_thread_manager)
    mock_agency_instance.agents[agent.name] = agent

    # Mock thread
    mock_thread = MagicMock()
    mock_thread.items = []
    mock_thread_manager.get_thread.return_value = mock_thread

    # Mock Runner.run
    mock_run_result = MagicMock()
    mock_run_result.new_items = []
    mock_run_result.final_output = "Valid response"

    with patch("agency_swarm.agent.Runner.run", new_callable=AsyncMock) as mock_runner:
        mock_runner.return_value = mock_run_result
        result = await agent.get_response("Test message")
        assert result == mock_run_result


@pytest.mark.asyncio
async def test_get_response_integrates_validation_fail(mock_thread_manager, mock_agency_instance):
    """Test that get_response integrates with response validation (failing case)."""
    # Use a real Agent instance with validation
    agent = Agent(name="TestAgent", instructions="Test", response_validator=validator_false)
    agent._set_agency_instance(mock_agency_instance)
    agent._set_thread_manager(mock_thread_manager)
    mock_agency_instance.agents[agent.name] = agent

    # Mock thread
    mock_thread = MagicMock()
    mock_thread.items = []
    mock_thread_manager.get_thread.return_value = mock_thread

    # Mock Runner.run
    mock_run_result = MagicMock()
    mock_run_result.new_items = []
    mock_run_result.final_output = "Invalid response"

    with patch("agency_swarm.agent.Runner.run", new_callable=AsyncMock) as mock_runner:
        mock_runner.return_value = mock_run_result
        result = await agent.get_response("Test message")
        # Should still return the result, but validation failure should be logged
        assert result == mock_run_result


@pytest.mark.asyncio
async def test_get_response_integrates_validation_raise(mock_thread_manager, mock_agency_instance):
    """Test that get_response integrates with response validation (exception case)."""
    # Use a real Agent instance with validation
    agent = Agent(name="TestAgent", instructions="Test", response_validator=validator_raises)
    agent._set_agency_instance(mock_agency_instance)
    agent._set_thread_manager(mock_thread_manager)
    mock_agency_instance.agents[agent.name] = agent

    # Mock thread
    mock_thread = MagicMock()
    mock_thread.items = []
    mock_thread_manager.get_thread.return_value = mock_thread

    # Mock Runner.run
    mock_run_result = MagicMock()
    mock_run_result.new_items = []
    mock_run_result.final_output = "Response that causes validation exception"

    with patch("agency_swarm.agent.Runner.run", new_callable=AsyncMock) as mock_runner:
        mock_runner.return_value = mock_run_result
        result = await agent.get_response("Test message")
        # Should still return the result, but validation exception should be handled
        assert result == mock_run_result

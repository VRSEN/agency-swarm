import warnings
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from agency_swarm import Agency, Agent


class TaskOutput(BaseModel):
    task_name: str = Field(..., description="Name of the task")
    status: str = Field(..., description="Status of the task")
    priority: int = Field(..., description="Priority level (1-5)")


@pytest.fixture
def mock_agent_with_output_type():
    """Agent with output_type for testing."""
    return Agent(name="OutputAgent", instructions="Test agent", output_type=TaskOutput)


@pytest.fixture
def mock_agent_without_output_type():
    """Agent without output_type for testing."""
    return Agent(name="BasicAgent", instructions="Basic test agent")


@pytest.fixture
def mock_agency_with_output_type(mock_agent_with_output_type):
    """Agency with an agent that has output_type."""
    return Agency(mock_agent_with_output_type)


@pytest.fixture
def mock_agency_without_output_type(mock_agent_without_output_type):
    """Agency with an agent that doesn't have output_type."""
    return Agency(mock_agent_without_output_type)


# --- Response Format Compatibility Tests ---


def test_agent_output_type_parameter():
    """Test that Agent properly accepts and stores output_type parameter."""
    agent = Agent(name="TestAgent", instructions="Test", output_type=TaskOutput)
    assert agent.output_type == TaskOutput


def test_agent_without_output_type():
    """Test that Agent without output_type has None."""
    agent = Agent(name="TestAgent", instructions="Test")
    assert agent.output_type is None


def test_agency_with_output_type_agent(mock_agency_with_output_type):
    """Test that Agency can be initialized with agents that have output_type."""
    agency = mock_agency_with_output_type
    assert len(agency.agents) == 1
    agent = list(agency.agents.values())[0]
    assert agent.output_type == TaskOutput


@pytest.mark.asyncio
async def test_get_completion_response_format_json_schema_warning(mock_agency_without_output_type):
    """Test that get_completion with response_format json_schema issues warning."""
    agency = mock_agency_without_output_type

    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "test_output",
            "schema": {
                "type": "object",
                "properties": {"message": {"type": "string"}, "priority": {"type": "integer"}},
                "required": ["message", "priority"],
            },
        },
    }

    # Mock the get_response method to avoid actual API calls
    with patch.object(agency, "get_response", new_callable=AsyncMock) as mock_get_response:
        mock_get_response.return_value = MagicMock(final_output="test response")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            # Also capture logger warnings
            with patch("agency_swarm.agency.logger") as mock_logger:
                await agency.get_completion(message="Test message", response_format=response_format)

                # Check that deprecation warning was issued
                deprecation_warnings = [warning for warning in w if issubclass(warning.category, DeprecationWarning)]
                assert len(deprecation_warnings) > 0
                assert any("get_completion" in str(warning.message) for warning in deprecation_warnings)

                # Check that response_format warning was logged
                mock_logger.warning.assert_called()
                warning_calls = [call for call in mock_logger.warning.call_args_list if "response_format" in str(call)]
                assert len(warning_calls) > 0

                # Verify get_response was called with response_format in kwargs
                mock_get_response.assert_called_once()
                call_kwargs = mock_get_response.call_args[1]
                assert "response_format" in call_kwargs
                assert call_kwargs["response_format"] == response_format


@pytest.mark.asyncio
async def test_get_completion_response_format_json_object_warning(mock_agency_without_output_type):
    """Test that get_completion with response_format json_object issues warning."""
    agency = mock_agency_without_output_type

    response_format = {"type": "json_object"}

    # Mock the get_response method to avoid actual API calls
    with patch.object(agency, "get_response", new_callable=AsyncMock) as mock_get_response:
        mock_get_response.return_value = MagicMock(final_output="test response")

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")

            # Also capture logger warnings
            with patch("agency_swarm.agency.logger") as mock_logger:
                await agency.get_completion(message="Test message", response_format=response_format)

                # Check that response_format warning was logged
                mock_logger.warning.assert_called()
                warning_calls = [call for call in mock_logger.warning.call_args_list if "response_format" in str(call)]
                assert len(warning_calls) > 0

                # Verify get_response was called with response_format in kwargs
                mock_get_response.assert_called_once()
                call_kwargs = mock_get_response.call_args[1]
                assert "response_format" in call_kwargs
                assert call_kwargs["response_format"] == response_format


@pytest.mark.asyncio
async def test_get_completion_invalid_response_format_warning(mock_agency_without_output_type):
    """Test that get_completion with invalid response_format issues warning and ignores it."""
    agency = mock_agency_without_output_type

    # Invalid response_format (unsupported type)
    response_format = {"type": "unsupported_type"}

    # Mock the get_response method to avoid actual API calls
    with patch.object(agency, "get_response", new_callable=AsyncMock) as mock_get_response:
        mock_get_response.return_value = MagicMock(final_output="test response")

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")

            # Also capture logger warnings
            with patch("agency_swarm.agency.logger") as mock_logger:
                await agency.get_completion(message="Test message", response_format=response_format)

                # Check that warning was logged for unsupported type
                mock_logger.warning.assert_called()
                warning_calls = [
                    call
                    for call in mock_logger.warning.call_args_list
                    if "Unsupported response_format type" in str(call)
                ]
                assert len(warning_calls) > 0

                # Verify get_response was called without response_format in kwargs (ignored)
                mock_get_response.assert_called_once()
                call_kwargs = mock_get_response.call_args[1]
                assert "response_format" not in call_kwargs


@pytest.mark.asyncio
async def test_get_completion_non_dict_response_format_warning(mock_agency_without_output_type):
    """Test that get_completion with non-dict response_format issues warning and ignores it."""
    agency = mock_agency_without_output_type

    # Invalid response_format (not a dict)
    response_format = "invalid_format"

    # Mock the get_response method to avoid actual API calls
    with patch.object(agency, "get_response", new_callable=AsyncMock) as mock_get_response:
        mock_get_response.return_value = MagicMock(final_output="test response")

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")

            # Also capture logger warnings
            with patch("agency_swarm.agency.logger") as mock_logger:
                await agency.get_completion(message="Test message", response_format=response_format)

                # Check that warning was logged for non-dict format
                mock_logger.warning.assert_called()
                warning_calls = [
                    call
                    for call in mock_logger.warning.call_args_list
                    if "response_format must be a dictionary" in str(call)
                ]
                assert len(warning_calls) > 0

                # Verify get_response was called without response_format in kwargs (ignored)
                mock_get_response.assert_called_once()
                call_kwargs = mock_get_response.call_args[1]
                assert "response_format" not in call_kwargs


@pytest.mark.asyncio
async def test_get_completion_empty_schema_warning(mock_agency_without_output_type):
    """Test that get_completion with empty schema in response_format issues warning and ignores it."""
    agency = mock_agency_without_output_type

    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "test_output",
            "schema": {},  # Empty schema
        },
    }

    # Mock the get_response method to avoid actual API calls
    with patch.object(agency, "get_response", new_callable=AsyncMock) as mock_get_response:
        mock_get_response.return_value = MagicMock(final_output="test response")

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")

            # Also capture logger warnings
            with patch("agency_swarm.agency.logger") as mock_logger:
                await agency.get_completion(message="Test message", response_format=response_format)

                # Check that warning was logged for empty schema
                mock_logger.warning.assert_called()
                warning_calls = [call for call in mock_logger.warning.call_args_list if "no schema found" in str(call)]
                assert len(warning_calls) > 0

                # Verify get_response was called without response_format in kwargs (ignored)
                mock_get_response.assert_called_once()
                call_kwargs = mock_get_response.call_args[1]
                assert "response_format" not in call_kwargs


def test_agency_method_signatures_compatibility():
    """Test that Agency method signatures are compatible with Agent signatures."""
    import inspect

    # Create test instances
    agent = Agent(name="TestAgent", instructions="Test")
    agency = Agency(agent)

    # Check get_response signatures
    agency_get_response_sig = inspect.signature(agency.get_response)
    agent_get_response_sig = inspect.signature(agent.get_response)

    agency_params = set(agency_get_response_sig.parameters.keys())
    agent_params = set(agent_get_response_sig.parameters.keys())

    # Agency should have most of the same parameters (excluding sender_name which is internal)
    expected_common_params = {"message", "context_override", "hooks_override", "run_config", "file_ids"}

    for param in expected_common_params:
        if param in agent_params:
            assert param in agency_params, f"Agency.get_response missing parameter: {param}"

    # Check get_response_stream signatures
    agency_stream_sig = inspect.signature(agency.get_response_stream)
    agent_stream_sig = inspect.signature(agent.get_response_stream)

    agency_stream_params = set(agency_stream_sig.parameters.keys())
    agent_stream_params = set(agent_stream_sig.parameters.keys())

    for param in expected_common_params:
        if param in agent_stream_params:
            assert param in agency_stream_params, f"Agency.get_response_stream missing parameter: {param}"

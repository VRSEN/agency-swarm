from unittest.mock import AsyncMock, MagicMock

import pytest

from agency_swarm import Agency, Agent

# --- Fixtures ---


@pytest.fixture
def mock_agent():
    """Provides a mocked Agent instance for testing."""
    agent = MagicMock(spec=Agent)
    agent.name = "MockAgent"
    agent.get_response = AsyncMock()
    agent.get_response_stream = AsyncMock()
    return agent


# --- Deprecated Method Tests ---


def test_agency_get_completion_calls_get_response(mock_agent):
    """Test that deprecated get_completion method calls get_response."""
    chart = [mock_agent]
    agency = Agency(agency_chart=chart)

    mock_agent.get_response.return_value = MagicMock(final_output="Test response")

    with pytest.warns(DeprecationWarning, match="Method 'get_completion' is deprecated"):
        result = agency.get_completion("Test message")

    assert result == "Test response"
    # Should call get_response on the first agent in the chart
    mock_agent.get_response.assert_called_once()

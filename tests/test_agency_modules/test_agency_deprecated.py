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


@pytest.mark.asyncio
async def test_agency_get_completion_calls_get_response(mock_agent):
    """Test that deprecated get_completion method calls get_response."""
    chart = [mock_agent]
    agency = Agency(agency_chart=chart)

    mock_agent.get_response.return_value = MagicMock(final_output="Test response")

    with pytest.warns(DeprecationWarning, match="Method 'get_completion' is deprecated"):
        result = await agency.get_completion("Test message")

    assert result == "Test response"
    # Should call get_response on the first agent in the chart
    mock_agent.get_response.assert_called_once()


@pytest.mark.asyncio
async def test_agency_get_completion_stream_calls_get_response_stream(mock_agent):
    """Test that deprecated get_completion_stream method calls get_response_stream."""
    chart = [mock_agent]
    agency = Agency(agency_chart=chart)

    async def mock_stream():
        yield {"event": "text", "data": "Hello"}
        yield {"event": "done"}

    # Configure the mock to return the async generator directly
    async def mock_get_response_stream(*args, **kwargs):
        async for event in mock_stream():
            yield event

    mock_agent.get_response_stream = mock_get_response_stream

    events = []
    with pytest.warns(DeprecationWarning, match="Method 'get_completion_stream' is deprecated"):
        async for event in agency.get_completion_stream("Test message", "MockAgent"):
            events.append(event)

    assert len(events) == 1  # Only text events are yielded by get_completion_stream
    assert events[0] == "Hello"

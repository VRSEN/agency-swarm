from unittest.mock import AsyncMock, MagicMock

import pytest
from agents import RunHooks

from agency_swarm import Agency, Agent

# --- Fixtures ---


@pytest.fixture
def mock_agent():
    """Provides a mocked Agent instance for testing."""
    agent = MagicMock(spec=Agent)
    agent.name = "MockAgent"
    agent.get_response = AsyncMock()
    agent.get_response_stream = AsyncMock()
    agent.send_message_tool_class = None  # Add missing attribute
    return agent


@pytest.fixture
def mock_agent2():
    """Provides a second mocked Agent instance for testing."""
    agent = MagicMock(spec=Agent)
    agent.name = "MockAgent2"
    agent.get_response = AsyncMock()
    agent.get_response_stream = AsyncMock()
    agent.send_message_tool_class = None  # Add missing attribute

    return agent


# --- Agency Response Method Tests ---


@pytest.mark.asyncio
async def test_agency_get_response_basic(mock_agent):
    """Test basic Agency.get_response functionality."""
    agency = Agency(mock_agent)
    mock_agent.get_response.return_value = MagicMock(final_output="Test response")

    result = await agency.get_response("Test message", "MockAgent")

    assert result.final_output == "Test response"
    mock_agent.get_response.assert_called_once()


@pytest.mark.asyncio
async def test_agency_get_response_with_hooks(mock_agent):
    """Test Agency.get_response with hooks."""
    mock_load_cb = MagicMock()
    mock_save_cb = MagicMock()
    agency = Agency(mock_agent, load_threads_callback=mock_load_cb, save_threads_callback=mock_save_cb)

    mock_agent.get_response.return_value = MagicMock(final_output="Test response")
    hooks_override = MagicMock(spec=RunHooks)

    result = await agency.get_response("Test message", "MockAgent", hooks_override=hooks_override)

    assert result.final_output == "Test response"
    mock_agent.get_response.assert_called_once()


@pytest.mark.asyncio
async def test_agency_get_response_invalid_recipient_warning(mock_agent):
    """Test Agency.get_response with invalid recipient agent name."""
    agency = Agency(mock_agent)

    with pytest.raises(ValueError, match="Agent with name 'InvalidAgent' not found"):
        await agency.get_response("Test message", "InvalidAgent")


@pytest.mark.asyncio
async def test_agency_get_response_stream_basic(mock_agent):
    """Test basic Agency.get_response_stream functionality."""
    agency = Agency(mock_agent)

    async def mock_stream():
        yield {"event": "text", "data": "Hello"}
        yield {"event": "done"}

    # Configure the mock to return the async generator directly
    async def mock_get_response_stream(*args, **kwargs):
        async for event in mock_stream():
            yield event

    mock_agent.get_response_stream = mock_get_response_stream

    events = []
    async for event in agency.get_response_stream("Test message", "MockAgent"):
        events.append(event)

    assert len(events) == 2
    assert events[0]["event"] == "text"
    assert events[1]["event"] == "done"


@pytest.mark.asyncio
async def test_agency_get_response_stream_with_hooks(mock_agent):
    """Test Agency.get_response_stream with hooks."""
    mock_load_cb = MagicMock()
    mock_save_cb = MagicMock()
    agency = Agency(mock_agent, load_threads_callback=mock_load_cb, save_threads_callback=mock_save_cb)

    async def mock_stream():
        yield {"event": "text", "data": "Hello"}
        yield {"event": "done"}

    # Configure the mock to return the async generator directly
    async def mock_get_response_stream(*args, **kwargs):
        async for event in mock_stream():
            yield event

    mock_agent.get_response_stream = mock_get_response_stream
    hooks_override = MagicMock(spec=RunHooks)

    events = []
    async for event in agency.get_response_stream("Test message", "MockAgent", hooks_override=hooks_override):
        events.append(event)

    assert len(events) == 2


@pytest.mark.asyncio
async def test_agency_agent_to_agent_communication(mock_agent, mock_agent2):
    """Test agent-to-agent communication through Agency."""
    agency = Agency(mock_agent, communication_flows=[(mock_agent, mock_agent2)])

    # Mock the first agent to call the second agent
    mock_agent.get_response.return_value = MagicMock(final_output="Response from MockAgent")
    mock_agent2.get_response.return_value = MagicMock(final_output="Response from MockAgent2")

    result = await agency.get_response("Test message", "MockAgent")

    assert result.final_output == "Response from MockAgent"
    mock_agent.get_response.assert_called_once()


@pytest.mark.asyncio
async def test_agent_communication_context_hooks_propagation(mock_agent, mock_agent2):
    """Test that context and hooks are properly propagated in agent communication."""
    mock_load_cb = MagicMock()
    mock_save_cb = MagicMock()
    agency = Agency(
        mock_agent,
        communication_flows=[(mock_agent, mock_agent2)],
        load_threads_callback=mock_load_cb,
        save_threads_callback=mock_save_cb,
    )

    mock_agent.get_response.return_value = MagicMock(final_output="Test response")
    context_override = {"test_key": "test_value"}
    hooks_override = MagicMock(spec=RunHooks)

    result = await agency.get_response(
        "Test message", "MockAgent", context_override=context_override, hooks_override=hooks_override
    )

    assert result.final_output == "Test response"
    mock_agent.get_response.assert_called_once()
    call_kwargs = mock_agent.get_response.call_args[1]
    assert "context_override" in call_kwargs
    assert "hooks_override" in call_kwargs

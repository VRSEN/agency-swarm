from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents import RunConfig, RunHooks

from agency_swarm import Agent
from agency_swarm.agent.core import AgencyContext

# --- Core Response Tests ---


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_get_response_saves_messages(mock_runner_run, minimal_agent, mock_thread_manager):
    """Test that get_response saves messages to the thread manager."""
    mock_runner_run.return_value = MagicMock(new_items=[], final_output="Test response")

    result = await minimal_agent.get_response("Test message")

    assert result is not None
    # Verify that messages were added to the thread manager
    mock_thread_manager.add_messages.assert_called()
    # Messages should be saved with proper agent metadata
    call_args = mock_thread_manager.add_messages.call_args[0]
    messages = call_args[0]
    assert len(messages) > 0
    # Check that messages have the agent metadata
    for msg in messages:
        assert msg.get("agent") == "TestAgent"


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_get_response_agent_to_agent_communication(mock_runner_run, minimal_agent, mock_thread_manager):
    """Test that get_response works correctly for agent-to-agent communication."""

    mock_runner_run.return_value = MagicMock(new_items=[], final_output="Test response")

    # Mock the agency instance and context for agent-to-agent communication
    mock_agency = MagicMock()
    mock_agency.agents = {"SomeAgent": MagicMock(name="SomeAgent")}
    mock_agency.user_context = {}

    agency_context = AgencyContext(
        agency_instance=mock_agency,
        thread_manager=mock_thread_manager,
        subagents={},
        load_threads_callback=None,
        save_threads_callback=None,
        shared_instructions=None,
    )

    result = await minimal_agent.get_response("Test message", sender_name="SomeAgent", agency_context=agency_context)

    assert result is not None
    # Verify that messages were added with proper sender metadata
    mock_thread_manager.add_messages.assert_called()
    call_args = mock_thread_manager.add_messages.call_args[0]
    messages = call_args[0]
    assert len(messages) > 0
    # Check that messages have the correct agent and callerAgent metadata
    for msg in messages:
        assert msg.get("agent") == "TestAgent"
        assert msg.get("callerAgent") == "SomeAgent"


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_get_response_with_overrides(mock_runner_run, minimal_agent):
    """Test get_response with context and hooks overrides."""
    mock_runner_run.return_value = MagicMock(new_items=[], final_output="Test response")
    context_override = {"test_key": "test_value"}
    hooks_override = MagicMock(spec=RunHooks)
    run_config = RunConfig()

    result = await minimal_agent.get_response(
        "Test message",
        context_override=context_override,
        hooks_override=hooks_override,
        run_config_override=run_config,
    )

    assert result is not None
    mock_runner_run.assert_called_once()
    # Verify that the context and hooks were passed to Runner.run
    call_kwargs = mock_runner_run.call_args[1]
    assert "context" in call_kwargs
    assert "hooks" in call_kwargs
    assert call_kwargs["hooks"] == hooks_override
    assert "run_config" in call_kwargs
    assert call_kwargs["run_config"] == run_config


@pytest.mark.asyncio
async def test_get_response_missing_thread_manager():
    """Test that a standalone agent auto-creates minimal context."""
    agent = Agent(name="TestAgent", instructions="Test")

    with patch("agents.Runner.run", new_callable=AsyncMock) as mock_runner:
        mock_runner.return_value = MagicMock(new_items=[], final_output="Test response")

        result = await agent.get_response("Test message")

        assert result is not None

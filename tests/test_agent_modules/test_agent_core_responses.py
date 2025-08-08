from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents import RunConfig, RunHooks

from agency_swarm import Agent

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

    result = await minimal_agent.get_response("Test message", sender_name="SomeAgent")

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
    """Test that get_response succeeds by creating ThreadManager when missing."""
    agent = Agent(name="TestAgent", instructions="Test")
    # Don't set thread manager initially
    assert agent._thread_manager is None

    # The agent should now successfully create a ThreadManager via _ensure_thread_manager()
    # and create a minimal agency instance for compatibility
    with patch("agents.Runner.run", new_callable=AsyncMock) as mock_runner:
        mock_runner.return_value = MagicMock(new_items=[], final_output="Test response")

        # This should succeed by auto-creating necessary components
        result = await agent.get_response("Test message")

        # Verify ThreadManager was created
        assert agent._thread_manager is not None
        assert result is not None


# --- Error Handling Tests ---


@pytest.mark.asyncio
async def test_call_before_agency_setup():
    """Test that calling agent methods without agency setup succeeds by auto-creating components."""
    agent = Agent(name="TestAgent", instructions="Test")
    # Agent not set up with agency initially
    assert agent._agency_instance is None
    assert agent._thread_manager is None

    # The agent should auto-create necessary components for direct usage
    with patch("agents.Runner.run", new_callable=AsyncMock) as mock_runner:
        mock_runner.return_value = MagicMock(new_items=[], final_output="Test response")

        # This should succeed by auto-creating ThreadManager
        result = await agent.get_response("Test message")

        # Verify ThreadManager was created (agency_instance stays None in standalone mode)
        assert agent._thread_manager is not None
        assert agent._agency_instance is None  # Remains None in standalone mode
        assert result is not None

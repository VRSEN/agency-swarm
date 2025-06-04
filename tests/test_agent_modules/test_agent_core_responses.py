from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents import RunConfig, RunHooks

from agency_swarm import Agent

# --- Core Response Tests ---


@pytest.mark.asyncio
@patch("agency_swarm.agent.Runner.run", new_callable=AsyncMock)
async def test_get_response_generates_thread_id(mock_runner_run, minimal_agent, mock_thread_manager):
    """Test that get_response generates a consistent thread ID for user interactions."""
    mock_runner_run.return_value = MagicMock(new_items=[], final_output="Test response")
    result = await minimal_agent.get_response("Test message")
    assert result is not None
    # Verify that get_thread was called with the consistent user->agent format
    mock_thread_manager.get_thread.assert_called()
    call_args = mock_thread_manager.get_thread.call_args[0]
    assert len(call_args) == 1
    assert call_args[0] == "user->TestAgent"


@pytest.mark.asyncio
@patch("agency_swarm.agent.Runner.run", new_callable=AsyncMock)
async def test_get_response_agent_to_agent_communication(mock_runner_run, minimal_agent, mock_thread_manager):
    """Test that get_response works correctly for agent-to-agent communication."""
    mock_runner_run.return_value = MagicMock(new_items=[], final_output="Test response")

    result = await minimal_agent.get_response("Test message", sender_name="SomeAgent")

    assert result is not None
    # Verify that get_thread was called with the sender->recipient format
    mock_thread_manager.get_thread.assert_called_once()
    call_args = mock_thread_manager.get_thread.call_args[0]
    assert len(call_args) == 1
    # Should be in format "SomeAgent->TestAgent"
    assert call_args[0] == "SomeAgent->TestAgent"


@pytest.mark.asyncio
@patch("agency_swarm.agent.Runner.run", new_callable=AsyncMock)
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
        run_config=run_config,
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
    with patch("agency_swarm.agent.Runner.run", new_callable=AsyncMock) as mock_runner:
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
    with patch("agency_swarm.agent.Runner.run", new_callable=AsyncMock) as mock_runner:
        mock_runner.return_value = MagicMock(new_items=[], final_output="Test response")

        # This should succeed by auto-creating ThreadManager and minimal agency
        result = await agent.get_response("Test message")

        # Verify components were created
        assert agent._thread_manager is not None
        assert agent._agency_instance is not None
        assert result is not None


# --- File Handling Tests ---


@pytest.mark.asyncio
async def test_check_file_exists_no_vs_id():
    """Test check_file_exists when no vector store ID is associated."""
    agent = Agent(name="TestAgent", instructions="Test")
    # No files_folder set, so files_folder_path should be None
    result = await agent.check_file_exists("test.txt")
    assert result is None

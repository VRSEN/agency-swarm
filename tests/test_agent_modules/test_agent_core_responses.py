from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents import RunConfig, RunHooks

from agency_swarm import Agent

# --- Core Response Tests ---


@pytest.mark.asyncio
@patch("agency_swarm.agent.Runner.run", new_callable=AsyncMock)
async def test_get_response_generates_chat_id(mock_runner_run, minimal_agent, mock_thread_manager):
    """Test that get_response generates a chat_id when none is provided."""
    mock_runner_run.return_value = MagicMock(new_items=[], final_output="Test response")
    result = await minimal_agent.get_response("Test message")
    assert result is not None
    # Verify that get_thread was called with a generated chat_id
    mock_thread_manager.get_thread.assert_called()
    call_args = mock_thread_manager.get_thread.call_args[0]
    assert len(call_args) == 1
    assert call_args[0].startswith("chat_")


@pytest.mark.asyncio
async def test_get_response_requires_chat_id_for_agent_sender(minimal_agent):
    """Test that get_response requires chat_id when sender_name is provided."""
    with pytest.raises(ValueError, match="chat_id is required"):
        await minimal_agent.get_response("Test message", sender_name="SomeAgent")


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
        chat_id="test_chat",
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
    """Test that get_response raises error when thread manager is missing."""
    agent = Agent(name="TestAgent", instructions="Test")
    # Don't set thread manager
    with pytest.raises(RuntimeError, match="missing ThreadManager"):
        await agent.get_response("Test message")


# --- Error Handling Tests ---


@pytest.mark.asyncio
async def test_call_before_agency_setup():
    """Test that calling agent methods before agency setup raises appropriate errors."""
    agent = Agent(name="TestAgent", instructions="Test")
    # Agent not set up with agency, so should raise RuntimeError
    with pytest.raises(RuntimeError):
        await agent.get_response("Test message")


# --- File Handling Tests ---


@pytest.mark.asyncio
async def test_check_file_exists_no_vs_id():
    """Test check_file_exists when no vector store ID is associated."""
    agent = Agent(name="TestAgent", instructions="Test")
    # No files_folder set, so files_folder_path should be None
    result = await agent.check_file_exists("test.txt")
    assert result is None

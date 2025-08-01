"""
Test context preservation and thread management in agent-to-agent communication.

This test verifies that agent-to-agent communication works correctly with the
thread identifier system based on sender->recipient patterns for conversation
isolation and context management.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from agents import RunContextWrapper, RunResult

from agency_swarm import Agent
from agency_swarm.context import MasterContext
from agency_swarm.tools.send_message import SendMessage


@pytest.fixture
def mock_sender_agent():
    agent = MagicMock(spec=Agent)
    agent.name = "OrchestratorAgent"
    return agent


@pytest.fixture
def mock_recipient_agent():
    agent = MagicMock(spec=Agent)
    agent.name = "WorkerAgent"
    mock_run_result = RunResult(
        _last_agent=agent,
        input=[],
        new_items=[],
        raw_responses=[],
        input_guardrail_results=[],
        output_guardrail_results=[],
        final_output="Work completed",
        context_wrapper=MagicMock(spec=RunContextWrapper),
    )
    agent.get_response = AsyncMock(return_value=mock_run_result)
    return agent


@pytest.fixture
def master_context():
    """A master context for agent communication."""
    context = MagicMock(spec=MasterContext)
    context.user_context = {"user_id": "user_456", "session": "session_789"}
    return context


@pytest.fixture
def send_message_tool(mock_sender_agent, mock_recipient_agent):
    return SendMessage(
        tool_name=f"send_message_to_{mock_recipient_agent.name}",
        sender_agent=mock_sender_agent,
        recipient_agent=mock_recipient_agent,
    )


@pytest.mark.asyncio
async def test_send_message_communication(send_message_tool, mock_recipient_agent, master_context):
    """
    Test that agent-to-agent communication works correctly through SendMessage tools.
    The system uses sender->recipient thread identifiers automatically.
    """
    # Create wrapper with the master context
    wrapper = MagicMock(spec=RunContextWrapper)
    wrapper.context = master_context

    # Prepare the message arguments
    args_json = '{"my_primary_instructions": "Coordinate the task", "message": "Please process this user request", "additional_instructions": "Use the full conversation context"}'

    # Execute the SendMessage tool
    result = await send_message_tool.on_invoke_tool(wrapper, args_json)

    # Verify the result
    assert result == "Work completed"

    # Verify that the recipient agent receives the correct parameters
    mock_recipient_agent.get_response.assert_called_once_with(
        message="Please process this user request",
        sender_name="OrchestratorAgent",
        additional_instructions="Use the full conversation context",
    )


@pytest.mark.asyncio
async def test_thread_id_generation(send_message_tool, mock_recipient_agent, master_context):
    """
    Test that the system generates appropriate thread identifiers based on sender->recipient patterns.
    """
    wrapper = MagicMock(spec=RunContextWrapper)
    wrapper.context = master_context

    args_json = (
        '{"my_primary_instructions": "Test instructions", "message": "Test message", "additional_instructions": ""}'
    )

    await send_message_tool.on_invoke_tool(wrapper, args_json)

    # Verify that get_response was called with sender_name for thread identifier generation
    call_args = mock_recipient_agent.get_response.call_args
    assert call_args.kwargs["sender_name"] == "OrchestratorAgent"

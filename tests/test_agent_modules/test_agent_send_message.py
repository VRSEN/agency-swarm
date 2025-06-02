from unittest.mock import AsyncMock, MagicMock

import pytest
from agents import RunContextWrapper

from agency_swarm import Agent
from agency_swarm.agent import SEND_MESSAGE_TOOL_PREFIX
from agency_swarm.context import MasterContext

# --- Send Message Tool Tests ---


@pytest.mark.asyncio
async def test_invoke_send_message_tool_success(minimal_agent):
    """Test successful invocation of send_message tool."""
    # Set up recipient agent
    recipient = Agent(name="Recipient", instructions="Receive messages")
    minimal_agent.register_subagent(recipient)

    # Mock the recipient's get_response method
    mock_response = MagicMock()
    mock_response.final_output = "Response from recipient"
    recipient.get_response = AsyncMock(return_value=mock_response)

    # Find the send_message tool
    send_message_tool = None
    for tool in minimal_agent.tools:
        if hasattr(tool, "name") and tool.name == f"{SEND_MESSAGE_TOOL_PREFIX}Recipient":
            send_message_tool = tool
            break

    assert send_message_tool is not None, "Send message tool not found"

    # Mock the context
    mock_context = MagicMock(spec=RunContextWrapper)
    mock_master_context = MagicMock(spec=MasterContext)
    mock_master_context.user_context = {}  # Add user_context attribute
    mock_context.context = mock_master_context

    # Test the tool invocation with the required parameters
    input_json = '{"my_primary_instructions": "Test instructions", "message": "Hello recipient"}'
    result = await send_message_tool.on_invoke_tool(mock_context, input_json)

    assert "Response from recipient" in result
    recipient.get_response.assert_called_once()


@pytest.mark.asyncio
async def test_invoke_send_message_tool_arg_parse_error(minimal_agent):
    """Test send_message tool with invalid JSON arguments."""
    # Set up recipient agent
    recipient = Agent(name="Recipient", instructions="Receive messages")
    minimal_agent.register_subagent(recipient)

    # Find the send_message tool
    send_message_tool = None
    for tool in minimal_agent.tools:
        if hasattr(tool, "name") and tool.name == f"{SEND_MESSAGE_TOOL_PREFIX}Recipient":
            send_message_tool = tool
            break

    assert send_message_tool is not None, "Send message tool not found"

    # Mock the context
    mock_context = MagicMock(spec=RunContextWrapper)
    mock_master_context = MagicMock(spec=MasterContext)
    mock_master_context.user_context = {}  # Add user_context attribute
    mock_context.context = mock_master_context

    # Test with invalid JSON
    invalid_json = '{"message": "Hello recipient"'  # Missing closing brace
    result = await send_message_tool.on_invoke_tool(mock_context, invalid_json)

    assert "Error: Invalid arguments format" in result


@pytest.mark.asyncio
async def test_invoke_send_message_tool_missing_arg(minimal_agent):
    """Test send_message tool with missing required argument."""
    # Set up recipient agent
    recipient = Agent(name="Recipient", instructions="Receive messages")
    minimal_agent.register_subagent(recipient)

    # Find the send_message tool
    send_message_tool = None
    for tool in minimal_agent.tools:
        if hasattr(tool, "name") and tool.name == f"{SEND_MESSAGE_TOOL_PREFIX}Recipient":
            send_message_tool = tool
            break

    assert send_message_tool is not None, "Send message tool not found"

    # Mock the context
    mock_context = MagicMock(spec=RunContextWrapper)
    mock_master_context = MagicMock(spec=MasterContext)
    mock_master_context.user_context = {}  # Add user_context attribute
    mock_context.context = mock_master_context

    # Test with missing message argument
    missing_arg_json = '{"my_primary_instructions": "Test instructions"}'
    result = await send_message_tool.on_invoke_tool(mock_context, missing_arg_json)

    assert "Missing required parameter" in result


@pytest.mark.asyncio
async def test_invoke_send_message_tool_recipient_error(minimal_agent):
    """Test send_message tool when recipient raises an error."""
    # Set up recipient agent
    recipient = Agent(name="Recipient", instructions="Receive messages")
    minimal_agent.register_subagent(recipient)

    # Mock the recipient's get_response method to raise an error
    recipient.get_response = AsyncMock(side_effect=Exception("Recipient error"))

    # Find the send_message tool
    send_message_tool = None
    for tool in minimal_agent.tools:
        if hasattr(tool, "name") and tool.name == f"{SEND_MESSAGE_TOOL_PREFIX}Recipient":
            send_message_tool = tool
            break

    assert send_message_tool is not None, "Send message tool not found"

    # Mock the context
    mock_context = MagicMock(spec=RunContextWrapper)
    mock_master_context = MagicMock(spec=MasterContext)
    mock_master_context.user_context = {}  # Add user_context attribute
    mock_context.context = mock_master_context

    # Test the tool invocation
    input_json = '{"my_primary_instructions": "Test instructions", "message": "Hello recipient"}'
    result = await send_message_tool.on_invoke_tool(mock_context, input_json)

    assert "Error: Failed to get response from agent" in result
    assert "Recipient error" in result

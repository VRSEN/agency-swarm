from unittest.mock import AsyncMock, MagicMock

import pytest
from agents import RunContextWrapper, RunResult

from agency_swarm import Agent
from agency_swarm.context import MasterContext
from agency_swarm.thread import ThreadManager
from agency_swarm.tools.send_message import MESSAGE_PARAM, SendMessage

# --- Fixtures ---


@pytest.fixture
def mock_sender_agent():
    agent = MagicMock(spec=Agent)
    agent.name = "SenderAgent"
    return agent


@pytest.fixture
def mock_recipient_agent(mock_run_context_wrapper):
    agent = MagicMock(spec=Agent)
    agent.name = "RecipientAgent"
    # Provide minimal required args for RunResult
    mock_run_result = RunResult(
        _last_agent=agent,
        input=[],
        new_items=[],
        raw_responses=[],
        input_guardrail_results=[],
        output_guardrail_results=[],
        final_output="Response from recipient",
        context_wrapper=mock_run_context_wrapper,
    )
    agent.get_response = AsyncMock(return_value=mock_run_result)
    return agent


@pytest.fixture
def mock_master_context():
    context = MagicMock(spec=MasterContext)
    context.chat_id = "test_chat_123"
    context.user_context = {"user_key": "user_value"}
    return context


@pytest.fixture
def mock_run_context_wrapper(mock_master_context):
    wrapper = MagicMock(spec=RunContextWrapper)
    wrapper.context = mock_master_context
    return wrapper


@pytest.fixture
def mock_context():
    context = MagicMock(spec=MasterContext)
    context.agents = {}
    context.thread_manager = MagicMock(spec=ThreadManager)
    context.thread_manager.get_thread = MagicMock(return_value=MagicMock())
    context.thread_manager.add_items_and_save = AsyncMock()
    context.chat_id = "test_chat_123"
    context.user_context = {"user_key": "user_val"}
    return context


@pytest.fixture
def mock_wrapper(mock_context, mock_sender_agent):
    wrapper = MagicMock(spec=RunContextWrapper)
    wrapper.context = mock_context
    wrapper.hooks = MagicMock()
    wrapper.agent = mock_sender_agent
    return wrapper


@pytest.fixture
def specific_send_message_tool(mock_sender_agent, mock_recipient_agent):
    return SendMessage(
        sender_agent=mock_sender_agent,
        recipient_agent=mock_recipient_agent,
        tool_name="send_message_to_RecipientAgent",
        tool_description="Send message to RecipientAgent.",
    )


# --- Test Cases ---


@pytest.mark.asyncio
async def test_send_message_success(specific_send_message_tool, mock_wrapper, mock_recipient_agent, mock_context):
    message_content = "Test message"

    result = await specific_send_message_tool.on_invoke_tool(wrapper=mock_wrapper, **{MESSAGE_PARAM: message_content})

    assert result == "Response from recipient"
    mock_recipient_agent.get_response.assert_awaited_once_with(
        message=message_content,
        sender_name="SenderAgent",
        chat_id="test_chat_123",
        context_override=mock_context.user_context,
    )


@pytest.mark.asyncio
async def test_send_message_missing_message_param(specific_send_message_tool, mock_wrapper):
    result = await specific_send_message_tool.on_invoke_tool(wrapper=mock_wrapper, **{})

    assert f"Error: Missing required parameter '{MESSAGE_PARAM}'" in result


@pytest.mark.asyncio
async def test_send_message_missing_chat_id(specific_send_message_tool, mock_wrapper):
    mock_wrapper.context.chat_id = None
    message_content = "Test message"

    result = await specific_send_message_tool.on_invoke_tool(wrapper=mock_wrapper, **{MESSAGE_PARAM: message_content})

    assert "Error: Internal context error. Missing chat_id" in result


@pytest.mark.asyncio
async def test_send_message_target_agent_error(specific_send_message_tool, mock_wrapper, mock_recipient_agent):
    mock_recipient_agent.get_response.side_effect = RuntimeError("Target agent failed")
    message_content = "Test message"

    result = await specific_send_message_tool.on_invoke_tool(wrapper=mock_wrapper, **{MESSAGE_PARAM: message_content})

    assert "Error: Failed to get response from agent 'RecipientAgent'. Reason: Target agent failed" in result
    mock_recipient_agent.get_response.assert_awaited_once()


# TODO: Add tests for response validation aspects
# TODO: Add tests for context/hooks propagation (more complex, might need integration tests)
# TODO: Add parameterized tests for various message inputs (empty, long, special chars)
# TODO: Add tests for specific schema validation failures (if FunctionTool provides hooks)

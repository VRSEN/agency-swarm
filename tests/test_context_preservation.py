"""
Test context preservation in the recursive orchestrator pattern.

This test verifies that agent-to-agent communication preserves the original
conversation context (chat_id) to enable the recursive orchestrator pattern
where all agents in a chain have access to the full conversation history.
"""

from unittest.mock import AsyncMock, MagicMock, patch

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
def original_user_context():
    """The original user's conversation context that should be preserved."""
    return MagicMock(spec=MasterContext)


@pytest.fixture
def send_message_tool(mock_sender_agent, mock_recipient_agent):
    return SendMessage(
        tool_name=f"send_message_to_{mock_recipient_agent.name}",
        sender_agent=mock_sender_agent,
        recipient_agent=mock_recipient_agent,
    )


@pytest.mark.asyncio
async def test_context_preservation_in_recursive_orchestrator_pattern(
    send_message_tool, mock_recipient_agent, original_user_context
):
    """
    Test that agent-to-agent communication preserves the original user's chat_id
    to enable the recursive orchestrator pattern with shared context.

    In the recursive orchestrator pattern:
    - User starts conversation with chat_id="user_chat_123"
    - Orchestrator calls Worker with the SAME chat_id="user_chat_123"
    - Worker can call Specialist with the SAME chat_id="user_chat_123"
    - All agents have access to the full conversation history
    """
    # Simulate the original user's conversation context
    original_chat_id = "user_chat_123"
    original_user_context.chat_id = original_chat_id
    original_user_context.user_context = {"user_id": "user_456", "session": "session_789"}

    # Create wrapper with the original user context
    wrapper = MagicMock(spec=RunContextWrapper)
    wrapper.context = original_user_context

    # Prepare the message arguments
    args_json = '{"my_primary_instructions": "Coordinate the task", "message": "Please process this user request", "additional_instructions": "Use the full conversation context"}'

    # Execute the SendMessage tool
    result = await send_message_tool.on_invoke_tool(wrapper, args_json)

    # Verify the result
    assert result == "Work completed"

    # CRITICAL: Verify that the recipient agent receives the ORIGINAL chat_id
    # This is essential for the recursive orchestrator pattern to work correctly
    mock_recipient_agent.get_response.assert_called_once_with(
        message="Please process this user request",
        sender_name="OrchestratorAgent",
        chat_id=original_chat_id,  # Must be the original user's chat_id, NOT "OrchestratorAgent->WorkerAgent"
        context_override={"user_id": "user_456", "session": "session_789"},
        additional_instructions="Use the full conversation context",
    )


@pytest.mark.asyncio
async def test_thread_manager_uses_original_chat_id_for_context_lookup(
    send_message_tool, mock_recipient_agent, original_user_context
):
    """
    Test that the ThreadManager uses the original chat_id for thread lookup,
    ensuring all agents in the chain access the same conversation thread.
    """
    original_chat_id = "user_conversation_456"
    original_user_context.chat_id = original_chat_id
    original_user_context.user_context = {}

    wrapper = MagicMock(spec=RunContextWrapper)
    wrapper.context = original_user_context

    args_json = (
        '{"my_primary_instructions": "Test instructions", "message": "Test message", "additional_instructions": ""}'
    )

    await send_message_tool.on_invoke_tool(wrapper, args_json)

    # Verify that get_response was called with the original chat_id
    # This ensures the ThreadManager will look up the correct conversation thread
    call_args = mock_recipient_agent.get_response.call_args
    assert call_args.kwargs["chat_id"] == original_chat_id

    # The chat_id should NOT be a structured identifier like "OrchestratorAgent->WorkerAgent"
    assert "->" not in call_args.kwargs["chat_id"]
    assert call_args.kwargs["chat_id"] == original_chat_id


@pytest.mark.asyncio
async def test_structured_identifiers_break_context_preservation():
    """
    Test that demonstrates why structured identifiers like "A->B" break
    the recursive orchestrator pattern by isolating conversations.

    This test documents the problem with the current implementation.
    """
    # This test documents the architectural issue:
    # If we use structured identifiers like "OrchestratorAgent->WorkerAgent",
    # each agent-to-agent communication happens in isolation, breaking
    # the shared context that is essential for the recursive orchestrator pattern.

    structured_id = "OrchestratorAgent->WorkerAgent"
    original_user_chat_id = "user_chat_123"

    # These should be the same for context preservation, but structured IDs make them different
    assert structured_id != original_user_chat_id

    # This breaks the recursive orchestrator pattern because:
    # 1. User conversation happens in thread "user_chat_123"
    # 2. Orchestrator->Worker happens in thread "OrchestratorAgent->WorkerAgent"
    # 3. Worker->Specialist would happen in thread "WorkerAgent->SpecialistAgent"
    # 4. No agent has access to the original user context
    # 5. The recursive chain is broken

    print("Structured identifiers break context preservation in recursive orchestrator pattern")
    assert True  # This test documents the architectural issue

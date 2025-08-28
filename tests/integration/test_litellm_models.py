"""
Integration tests for litellm-patched agents.

These tests verify that agents are able to process
user and agent-to-agent messages without errors.
"""

import os

import pytest
from agents import ModelSettings
from agents.extensions.models.litellm_model import LitellmModel

from agency_swarm import Agency, Agent
from agency_swarm.tools.send_message import SendMessageHandoff


@pytest.fixture
def coordinator_agent():
    return Agent(
        name="Coordinator",
        instructions=(
            "You are a coordinator agent. Your job is to receive tasks and delegate them either via "
            "When you receive a task, use the `send_message` tool and select 'Worker' as the recipient "
            "to ask the Worker agent to perform the task. Always include the full "
            "task details in your message. "
            "When delegating, only relay the exact task text and never include unrelated user information."
        ),
        model_settings=ModelSettings(temperature=0.0),
        model=LitellmModel(model="openai/gpt-4.1", api_key=os.getenv("OPENAI_API_KEY")),
        send_message_tool_class=SendMessageHandoff,
    )


@pytest.fixture
def worker_agent():
    return Agent(
        name="Worker",
        instructions=("You perform tasks. When you receive a task, "),
        model_settings=ModelSettings(temperature=0.0),
        model=LitellmModel(model="openai/gpt-4.1", api_key=os.getenv("OPENAI_API_KEY")),
    )


@pytest.fixture
def data_agent():
    return Agent(
        name="DataAgent",
        instructions=(
            "You are a DataAgent that provides information about the user. User name is John Doe. User age is 30."
        ),
        description="Has information about the user.",
        model_settings=ModelSettings(temperature=0.0),
        model=LitellmModel(model="openai/gpt-4.1", api_key=os.getenv("OPENAI_API_KEY")),
    )


@pytest.fixture
def coordinator_worker_agency(coordinator_agent, worker_agent, data_agent) -> Agency:
    """Agency with coordinator->worker communication flow."""
    return Agency(
        coordinator_agent,
        worker_agent,
        communication_flows=[coordinator_agent > data_agent, worker_agent > data_agent],
        shared_instructions="Test agency for agent-to-agent persistence verification.",
    )


class TestLitellmModels:
    """Test suite for agent-to-agent conversation persistence."""

    @pytest.mark.asyncio
    async def test_agent_to_agent_messages(self, coordinator_worker_agency: Agency, worker_agent: Agent):
        """
        Verify all types of communication with patched agents
        """
        user_message = "Say hi to the data agent."
        # Step 1: Use a send message to check if it'll cause problems on handoff
        await coordinator_worker_agency.get_response(message=user_message, recipient_agent="Worker")

        user_message = "What is my name and age?"
        response = await coordinator_worker_agency.get_response(message=user_message, recipient_agent="Coordinator")
        processed_response = str(response.final_output).lower()
        assert "john" in processed_response and "doe" in processed_response, "Response should contain the user's name"
        assert "30" in processed_response or "thirty" in processed_response, "Response should contain the user's age"

        # Both agents will have user-facing messages, but will not have any agent-to-agent messages
        data_agent_messages = coordinator_worker_agency.thread_manager.get_conversation_history("DataAgent", None)
        coordinator_messages = coordinator_worker_agency.thread_manager.get_conversation_history("Coordinator", None)
        assert len(data_agent_messages) > 0, "Agent-to-agent messages should be created after communication"
        assert len(coordinator_messages) > 0, "Agent-to-agent messages should be created after communication"

        for i, item in enumerate(coordinator_messages):
            print(
                f"  Message {i + 1}: role={item.get('role')}, agent={item.get('agent')}, "
                f"callerAgent={item.get('callerAgent')}, content_preview={str(item)}..."
            )

        # Should contain a a transfer call
        function_calls = [msg for msg in coordinator_messages if msg.get("type") == "function_call"]
        assert len(function_calls) > 0, "Should have a function call to DataAgent"
        assistant_messages = [msg for msg in function_calls if "transfer_to_" in msg.get("name")]
        assert len(assistant_messages) > 0, "Should have at least one handoff"

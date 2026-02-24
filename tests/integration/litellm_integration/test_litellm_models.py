"""
Integration tests for litellm-patched agents.

These tests verify that agents are able to process
user and agent-to-agent messages without errors.
"""

import importlib
import os

import pytest
from agents import ModelSettings

from agency_swarm import Agency, Agent
from agency_swarm.tools.send_message import Handoff, SendMessage

pytest.importorskip("litellm")
LitellmModel = importlib.import_module("agents.extensions.models.litellm_model").LitellmModel


@pytest.fixture
def coordinator_agent():
    return Agent(
        name="Coordinator",
        instructions=(
            "For any user question about the user, call `transfer_to_DataAgent`. Always use the handoff tool to answer."
        ),
        model_settings=ModelSettings(tool_choice="required"),
        model=LitellmModel(model="openai/gpt-5-mini", api_key=os.getenv("OPENAI_API_KEY")),
    )


@pytest.fixture
def worker_agent():
    return Agent(
        name="Worker",
        instructions=(
            "For any user question about the user, use the `send_message` tool to ask DataAgent. "
            "Always use the tool to answer."
        ),
        model_settings=ModelSettings(tool_choice="required"),
        model=LitellmModel(model="openai/gpt-5-mini", api_key=os.getenv("OPENAI_API_KEY")),
    )


@pytest.fixture
def data_agent():
    return Agent(
        name="DataAgent",
        instructions="User name is John Doe. User age is 30. Answer with just the facts.",
        description="Has information about the user.",
        model=LitellmModel(model="openai/gpt-5-mini", api_key=os.getenv("OPENAI_API_KEY")),
    )


@pytest.fixture
def coordinator_worker_agency(coordinator_agent, worker_agent, data_agent) -> Agency:
    """Agency with coordinator->worker communication flow."""
    return Agency(
        coordinator_agent,
        worker_agent,
        communication_flows=[
            (coordinator_agent > data_agent, Handoff),
            (worker_agent > data_agent, SendMessage),
        ],
        shared_instructions="Test agency for agent-to-agent persistence verification.",
    )


class TestLitellmModels:
    """Test suite for agent-to-agent conversation persistence."""

    @pytest.mark.asyncio
    async def test_agent_to_agent_messages(self, coordinator_worker_agency: Agency, worker_agent: Agent):
        """
        Verify handoff communication works with litellm-patched agents.
        Coordinator uses transfer_to_DataAgent and Worker uses send_message.
        """
        worker_response = await coordinator_worker_agency.get_response(
            message="What is my name and age?",
            recipient_agent="Worker",
        )
        processed_response = str(worker_response.final_output).lower()
        assert "john" in processed_response and "doe" in processed_response, "Response should contain the user's name"
        assert "30" in processed_response or "thirty" in processed_response, "Response should contain the user's age"

        coordinator_response = await coordinator_worker_agency.get_response(
            message="What is my name and age?",
            recipient_agent="Coordinator",
        )
        processed_response = str(coordinator_response.final_output).lower()
        assert "john" in processed_response and "doe" in processed_response, "Response should contain the user's name"
        assert "30" in processed_response or "thirty" in processed_response, "Response should contain the user's age"

        # Verify conversation history was created for both paths
        handoff_messages = coordinator_worker_agency.thread_manager.get_conversation_history("DataAgent", None)
        send_message_messages = coordinator_worker_agency.thread_manager.get_conversation_history(
            "DataAgent",
            "Worker",
        )
        handoff_data_agent_messages = [msg for msg in handoff_messages if msg.get("agent") == "DataAgent"]
        send_message_data_agent_messages = [msg for msg in send_message_messages if msg.get("agent") == "DataAgent"]
        assert len(handoff_data_agent_messages) > 0, "DataAgent should have messages after handoff"
        assert len(send_message_data_agent_messages) > 0, "DataAgent should have messages after send_message"

        # Verify tool calls were created by both agents
        all_messages = coordinator_worker_agency.thread_manager.get_all_messages()
        function_calls = [msg for msg in all_messages if msg.get("type") == "function_call"]
        worker_send_messages = [
            msg for msg in function_calls if msg.get("agent") == "Worker" and msg.get("name") == "send_message"
        ]
        coordinator_handoffs = [
            msg for msg in function_calls if msg.get("agent") == "Coordinator" and "transfer_to_" in msg.get("name", "")
        ]
        assert len(worker_send_messages) > 0, "Worker should have at least one send_message call"
        assert len(coordinator_handoffs) > 0, "Coordinator should have at least one handoff"

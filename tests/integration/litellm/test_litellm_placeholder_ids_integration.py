"""
Integration test verifying LiteLLM placeholder IDs are normalized before persistence.

Requires live Anthropic access; skipped automatically when ANTHROPIC_API_KEY is not configured.
"""

import os

import litellm
import pytest
from agents.extensions.models.litellm_model import LitellmModel
from agents.models.fake_id import FAKE_RESPONSES_ID

from agency_swarm import Agency, Agent, ModelSettings, function_tool
from agency_swarm.tools.send_message import Handoff

pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY is required for LiteLLM integration test.",
)


def _build_agency() -> Agency:
    @function_tool
    def get_user_id(args: str) -> str:
        return "User id is 1245725189"

    coordinator_agent = Agent(
        name="Coordinator",
        instructions=(
            "You are a coordinator agent. Your job is to receive tasks and delegate them either via "
            "When you receive a task, use the `send_message` tool and select 'Worker' as the recipient "
            "to ask the Worker agent to perform the task. Always include the full "
            "task details in your message. "
            "When delegating, only relay the exact task text and never include unrelated user information."
        ),
        model_settings=ModelSettings(temperature=0.0),
        model=LitellmModel(model="anthropic/claude-sonnet-4-20250514"),
        send_message_tool_class=Handoff,
        tools=[get_user_id],
    )

    worker_agent = Agent(
        name="Worker",
        instructions="You perform tasks.",
        model_settings=ModelSettings(temperature=0.0),
        model=LitellmModel(model="anthropic/claude-sonnet-4-20250514"),
    )

    data_agent = Agent(
        name="DataAgent",
        instructions="You are a DataAgent that provides information about the user. \
        User name is John Doe. User age is 30.",
        description="Has information about the user.",
        model_settings=ModelSettings(temperature=0.0),
        model=LitellmModel(model="anthropic/claude-sonnet-4-20250514"),
    )

    return Agency(
        coordinator_agent,
        worker_agent,
        communication_flows=[coordinator_agent > data_agent, worker_agent > data_agent],
        shared_instructions="Test agency for agent-to-agent persistence verification.",
    )


def test_litellm_placeholder_ids_are_not_persisted() -> None:
    litellm.modify_params = True

    agency = _build_agency()

    agency.get_response_sync(message="Say hi to data agent")
    agency.get_response_sync(message="Hello")

    messages = agency.thread_manager.get_all_messages()
    placeholder_items = [msg for msg in messages if msg.get("id") == FAKE_RESPONSES_ID]

    assert len(messages) >= 6, "Expected multiple conversation items after two turns"
    assert not placeholder_items, "Placeholder IDs should not be persisted after normalization"

    call_ids = {msg.get("call_id") for msg in messages if msg.get("type") == "function_call_output"}
    assert len(call_ids) >= 1, "Tool call outputs should be captured with unique call_ids"

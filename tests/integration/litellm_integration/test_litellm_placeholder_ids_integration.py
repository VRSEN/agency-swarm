"""
Integration test verifying LiteLLM placeholder IDs are normalized before persistence.

Requires live Anthropic access; skipped automatically when ANTHROPIC_API_KEY is not configured.
"""

import importlib
import os

import pytest
from agents.models.fake_id import FAKE_RESPONSES_ID

from agency_swarm import Agency, Agent, ModelSettings, function_tool
from agency_swarm.tools.send_message import Handoff

litellm = pytest.importorskip("litellm")
LitellmModel = importlib.import_module("agents.extensions.models.litellm_model").LitellmModel

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
        communication_flows=[
            (coordinator_agent > data_agent, Handoff),
            (worker_agent > data_agent, Handoff),
        ],
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

    function_calls = [msg for msg in messages if msg.get("type") == "function_call"]
    function_outputs = [msg for msg in messages if msg.get("type") == "function_call_output"]

    function_call_ids = [msg.get("call_id") for msg in function_calls]
    output_call_ids = [msg.get("call_id") for msg in function_outputs]

    assert len(function_call_ids) >= 1, "Expected at least one function call in persisted history"
    assert all(isinstance(call_id, str) and call_id for call_id in function_call_ids)
    assert len(function_call_ids) == len(set(function_call_ids))
    assert set(function_call_ids) <= set(output_call_ids), "Each function call should have a matching output"

    for i, msg in enumerate(messages):
        if msg.get("type") != "function_call":
            continue
        call_id = msg.get("call_id")
        output_idx = None
        for j in range(i + 1, len(messages)):
            if messages[j].get("type") == "function_call_output" and messages[j].get("call_id") == call_id:
                output_idx = j
                break
        assert output_idx is not None, f"Missing function_call_output for call_id={call_id}"
        between = messages[i + 1 : output_idx]
        assistant_between = [item for item in between if item.get("role") == "assistant"]
        assert not assistant_between, "Tool call/results should remain consecutive without assistant inserts"

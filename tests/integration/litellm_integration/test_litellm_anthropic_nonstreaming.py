"""
Non-streaming version of Anthropic message ordering test.

Verifies correct message ordering in non-streaming mode.
"""

import importlib
import os

import pytest
from agents import ModelSettings
from agents.models.fake_id import FAKE_RESPONSES_ID

from agency_swarm import Agency, Agent, function_tool
from agency_swarm.tools.send_message import Handoff

litellm = pytest.importorskip("litellm")
LitellmModel = importlib.import_module("agents.extensions.models.litellm_model").LitellmModel

pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY required for Anthropic streaming test.",
)


@function_tool
def get_user_id(args: str) -> str:
    """Returns user ID for testing."""
    return "User id is 1245725189"


def _assert_valid_tool_call_pairs(messages: list[dict[str, object]]) -> None:
    function_calls = [msg for msg in messages if msg.get("type") == "function_call"]
    function_outputs = [msg for msg in messages if msg.get("type") == "function_call_output"]

    call_ids = [msg.get("call_id") for msg in function_calls]
    assert all(isinstance(call_id, str) and call_id for call_id in call_ids)
    assert len(call_ids) == len(set(call_ids))

    output_call_ids = [msg.get("call_id") for msg in function_outputs]
    assert all(isinstance(call_id, str) and call_id for call_id in output_call_ids)
    assert set(call_ids) <= set(output_call_ids)

    placeholder_items = [msg for msg in messages if msg.get("id") == FAKE_RESPONSES_ID]
    assert not placeholder_items, "Placeholder IDs should not persist in Anthropic/LiteLLM history"


@pytest.fixture(scope="function")
def litellm_anthropic_agency():
    coordinator = Agent(
        name="Coordinator",
        instructions="You are a coordinator agent.",
        model_settings=ModelSettings(temperature=0.0),
        model=LitellmModel(model="anthropic/claude-sonnet-4-20250514"),
        tools=[get_user_id],
    )

    worker = Agent(
        name="Worker",
        instructions="You perform tasks.",
        model_settings=ModelSettings(temperature=0.0),
        model=LitellmModel(model="anthropic/claude-sonnet-4-20250514"),
    )

    return Agency(
        coordinator,
        worker,
        communication_flows=[(coordinator > worker, Handoff)],
        shared_instructions="Test agency",
    )


class TestLitellmAnthropicNonStreamingMessageOrdering:
    """Verify no intermediate assistant messages persist during tool execution (non-streaming mode)."""

    @pytest.mark.asyncio
    async def test_tool_usage_no_intermediate_messages(self, litellm_anthropic_agency: Agency):
        """Verify tool usage preserves correct message sequence in non-streaming mode."""
        litellm.modify_params = True

        # First turn with tool usage
        await litellm_anthropic_agency.get_response(message="get my id")

        # Verify message structure
        messages = litellm_anthropic_agency.thread_manager.get_all_messages()
        _assert_valid_tool_call_pairs(messages)

        # Find all function_call and function_call_output pairs
        for i, msg in enumerate(messages):
            if msg.get("type") == "function_call":
                # Find corresponding function_call_output
                call_id = msg.get("call_id")
                output_idx = None
                for j in range(i + 1, len(messages)):
                    if messages[j].get("type") == "function_call_output" and messages[j].get("call_id") == call_id:
                        output_idx = j
                        break

                assert output_idx is not None, f"No function_call_output found for call_id {call_id}"

                # Check messages between function_call and function_call_output
                between = messages[i + 1 : output_idx]
                assistant_msgs = [m for m in between if m.get("role") == "assistant"]

                assert not assistant_msgs, (
                    f"Found {len(assistant_msgs)} intermediate assistant message(s) "
                    f"between function_call and function_call_output. This violates "
                    f"Anthropic's requirement for consecutive tool_use/tool_result pairs."
                )

        # Second turn should succeed
        await litellm_anthropic_agency.get_response(message="hi")

    @pytest.mark.asyncio
    async def test_handoff_no_intermediate_messages(self, litellm_anthropic_agency: Agency):
        """Verify handoff preserves correct message sequence in non-streaming mode."""
        litellm.modify_params = True

        # First turn with handoff
        await litellm_anthropic_agency.get_response(message="transfer to worker", recipient_agent="Coordinator")

        # Verify no intermediate assistant messages between tool calls and outputs
        messages = litellm_anthropic_agency.thread_manager.get_all_messages()
        _assert_valid_tool_call_pairs(messages)

        for i, msg in enumerate(messages):
            if msg.get("type") == "function_call":
                call_id = msg.get("call_id")
                output_idx = None
                for j in range(i + 1, len(messages)):
                    if messages[j].get("type") == "function_call_output" and messages[j].get("call_id") == call_id:
                        output_idx = j
                        break

                if output_idx is not None:
                    between = messages[i + 1 : output_idx]
                    assistant_msgs = [m for m in between if m.get("role") == "assistant"]

                    assert not assistant_msgs, (
                        "Found intermediate assistant message(s) during handoff "
                        "that would violate Anthropic API requirements."
                    )

        # Second turn should succeed
        await litellm_anthropic_agency.get_response(message="hi")

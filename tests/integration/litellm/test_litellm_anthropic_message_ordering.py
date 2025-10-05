"""
Regression test for LiteLLM/Anthropic message ordering bug.

Bug: After upgrading to openai-agents 0.3.x, streaming mode with LiteLLM/Anthropic
would fail on the second turn with:
  "tool_use ids were found without tool_result blocks immediately after..."

Root cause: Intermediate assistant messages during tool execution were persisted,
breaking Anthropic's requirement for consecutive tool_use/tool_result pairs.

This test verifies the fix: intermediate assistant messages are NOT persisted
during tool execution, maintaining the correct sequence for Anthropic API.
"""

import os

import pytest
from agents import ModelSettings
from agents.extensions.models.litellm_model import LitellmModel

from agency_swarm import Agency, Agent, function_tool
from agency_swarm.tools.send_message import SendMessageHandoff

pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY required for Anthropic streaming test.",
)


@function_tool
def get_user_id(args: str) -> str:
    """Returns user ID for testing."""
    return "User id is 1245725189"


@pytest.fixture(scope="function")
def litellm_anthropic_agency():
    """Agency setup matching litellm_test.py reproduction case."""
    coordinator = Agent(
        name="Coordinator",
        instructions="You are a coordinator agent.",
        model_settings=ModelSettings(temperature=0.0),
        model=LitellmModel(model="anthropic/claude-sonnet-4-20250514"),
        send_message_tool_class=SendMessageHandoff,
        tools=[get_user_id],
    )

    worker = Agent(
        name="Worker",
        instructions="You perform tasks.",
        model_settings=ModelSettings(temperature=0.0),
        model=LitellmModel(model="anthropic/claude-sonnet-4-20250514"),
    )

    data_agent = Agent(
        name="DataAgent",
        instructions="You are a DataAgent. User name is John Doe. User age is 30.",
        description="Has information about the user.",
        model_settings=ModelSettings(temperature=0.0),
        model=LitellmModel(model="anthropic/claude-sonnet-4-20250514"),
    )

    return Agency(
        coordinator,
        worker,
        communication_flows=[coordinator > data_agent, worker > data_agent],
        shared_instructions="Test agency",
    )


class TestLitellmAnthropicMessageOrdering:
    """Verify no intermediate assistant messages persist during tool execution."""

    @pytest.mark.asyncio
    async def test_tool_usage_no_intermediate_messages(self, litellm_anthropic_agency: Agency):
        """
        Verify tool usage preserves correct message sequence.

        Bug scenario: After tool call, second streaming turn would fail because
        intermediate assistant message broke the function_call → function_call_output sequence.

        Reproduces litellm_test.py: streaming mode, tool usage, then follow-up message.
        """
        import litellm

        litellm.modify_params = True

        # First turn: trigger tool usage (streaming mode - matches litellm_test.py)
        async for _ in litellm_anthropic_agency.get_response_stream(message="get my id"):
            pass

        # Verify message structure
        messages = litellm_anthropic_agency.thread_manager.get_all_messages()

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

        # Second turn should succeed without Anthropic API errors (streaming mode)
        async for _ in litellm_anthropic_agency.get_response_stream(message="hi"):
            pass

    @pytest.mark.asyncio
    async def test_handoff_no_intermediate_messages(self, litellm_anthropic_agency: Agency):
        """
        Verify handoff preserves correct message sequence.

        Bug scenario: After handoff, second streaming turn would fail due to
        duplicate tool_use IDs or missing tool_result blocks.
        """
        import litellm

        litellm.modify_params = True

        # First turn: trigger handoff (streaming mode - matches litellm_test.py line 86)
        async for _ in litellm_anthropic_agency.get_response_stream(
            message="transfer to worker", recipient_agent="Coordinator"
        ):
            pass

        # Verify no intermediate assistant messages between tool calls and outputs
        messages = litellm_anthropic_agency.thread_manager.get_all_messages()

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

        # Second turn should succeed (streaming mode)
        async for _ in litellm_anthropic_agency.get_response_stream(message="hi"):
            pass

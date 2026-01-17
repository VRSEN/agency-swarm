import pytest
from agents import HandoffInputData
from agents.extensions.models.litellm_model import LitellmModel
from agents.items import ToolCallItem
from agents.models.fake_id import FAKE_RESPONSES_ID
from agents.models.openai_responses import OpenAIResponsesModel
from openai import AsyncOpenAI
from openai.types.responses import ResponseFunctionToolCall

from agency_swarm import Agent
from agency_swarm.tools.send_message import SendMessageHandoff


@pytest.mark.asyncio
async def test_handoff_to_litellm_strips_hosted_tool_history_items_and_injects_note():
    recipient = Agent(
        name="RecipientLiteLLM",
        instructions="You are a helpful assistant.",
        model=LitellmModel(model="openai/gpt-5.2", api_key="test-key"),
    )
    handoff_builder = SendMessageHandoff()
    handoff_builder.add_reminder = False
    handoff_tool = handoff_builder.create_handoff(recipient)
    assert handoff_tool.input_filter is not None

    input_data = HandoffInputData(
        input_history=[
            {"type": "mcp_list_tools_item", "id": "mcp_list_1", "server_label": "srv", "tools": []},
            {"type": "local_shell_call_output", "call_id": "call_local_shell_1", "output": [{"type": "output_text"}]},
            {"type": "message", "role": "assistant", "content": "hi"},
        ],
        pre_handoff_items=(),
        new_items=(),
        run_context=None,
    )

    filtered = await handoff_tool.input_filter(input_data)
    assert isinstance(filtered.input_history, tuple)
    assert filtered.input_history[0]["role"] == "system"
    assert "Removed types:" in filtered.input_history[0]["content"]
    removed = {"mcp_list_tools_item", "local_shell_call_output"}
    assert all(item.get("type") not in removed for item in filtered.input_history)


@pytest.mark.asyncio
async def test_handoff_to_openai_drops_reasoning_and_normalizes_ids():
    recipient = Agent(
        name="RecipientOpenAI",
        instructions="You are a helpful assistant.",
        model=OpenAIResponsesModel(model="gpt-5.2", openai_client=AsyncOpenAI(api_key="test-key")),
    )
    handoff_builder = SendMessageHandoff()
    handoff_builder.add_reminder = False
    handoff_tool = handoff_builder.create_handoff(recipient)
    assert handoff_tool.input_filter is not None

    sender = Agent(name="Sender", instructions="You are a helpful assistant.")
    # BaseModel raw_item with Anthropic-style tool-call id (OpenAI rejects toolu_* ids).
    base_model_call = ResponseFunctionToolCall(
        type="function_call",
        id="toolu_01TESTCALLID",
        call_id="call_test_1",
        name="noop",
        arguments="{}",
    )
    run_item = ToolCallItem(agent=sender, raw_item=base_model_call)

    input_data = HandoffInputData(
        input_history=[
            {"type": "reasoning", "id": "rs_1", "content": [{"type": "output_text", "text": "Reasoning text"}]},
            {"type": "message", "role": "assistant", "id": FAKE_RESPONSES_ID, "content": "hi"},
            {
                "type": "function_call",
                "id": "toolu_01ANOTHER",
                "call_id": "call_test_2",
                "name": "noop",
                "arguments": "{}",
            },
        ],
        pre_handoff_items=(run_item,),
        new_items=(),
        run_context=None,
    )

    filtered = await handoff_tool.input_filter(input_data)

    assert isinstance(filtered.input_history, tuple)
    assert all(item.get("type") != "reasoning" for item in filtered.input_history)
    # No placeholder / provider-specific IDs should remain in history dicts.
    for item in filtered.input_history:
        item_id = item.get("id")
        if isinstance(item_id, str):
            assert item_id != FAKE_RESPONSES_ID
            assert not item_id.startswith("toolu_")

    # RunItem raw id should be rewritten away from toolu_*
    raw = filtered.pre_handoff_items[0].raw_item
    raw_id = getattr(raw, "id", None)
    assert isinstance(raw_id, str)
    assert not raw_id.startswith("toolu_")
    assert raw_id != FAKE_RESPONSES_ID


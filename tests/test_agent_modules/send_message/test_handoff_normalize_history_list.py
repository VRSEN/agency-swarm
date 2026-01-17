import pytest
from agents import HandoffInputData, RunContextWrapper
from agents.items import MCPListToolsItem, ToolCallItem, ToolCallOutputItem
from agents.models.fake_id import FAKE_RESPONSES_ID
from agents.models.openai_responses import OpenAIResponsesModel
from openai import AsyncOpenAI
from openai.types.responses import ResponseFunctionToolCall
from openai.types.responses.response_output_item import McpListTools

from agency_swarm import Agent
from agency_swarm.context import MasterContext
from agency_swarm.tools.send_message import SendMessageHandoff
from agency_swarm.utils.thread import ThreadManager


@pytest.mark.asyncio
async def test_handoff_normalizes_ids_when_input_history_is_list_and_add_reminder_false():
    recipient = Agent(name="Recipient", instructions="You are a helpful assistant.")
    handoff_builder = SendMessageHandoff()
    handoff_builder.add_reminder = False
    handoff_tool = handoff_builder.create_handoff(recipient)
    assert handoff_tool.input_filter is not None

    # NOTE: HandoffInputData.input_history is typed as str|tuple, but at runtime it can still be
    # a list (e.g., when caller code builds history dynamically). We harden normalization for that.
    input_data = HandoffInputData(
        input_history=[{"type": "message", "role": "assistant", "id": FAKE_RESPONSES_ID, "content": "hi"}],
        pre_handoff_items=(),
        new_items=(),
        run_context=None,
    )

    filtered = await handoff_tool.input_filter(input_data)

    assert isinstance(filtered.input_history, tuple)
    assert filtered.input_history[0]["id"] != FAKE_RESPONSES_ID
    assert filtered.input_history[0]["id"].startswith("msg_")


@pytest.mark.asyncio
async def test_handoff_drops_reasoning_items_only_when_recipient_is_openai():
    recipient = Agent(
        name="RecipientOpenAI",
        instructions="You are a helpful assistant.",
        model=OpenAIResponsesModel(model="gpt-5.2", openai_client=AsyncOpenAI(api_key="test-key")),
    )
    handoff_builder = SendMessageHandoff()
    handoff_builder.add_reminder = False
    handoff_tool = handoff_builder.create_handoff(recipient)
    assert handoff_tool.input_filter is not None

    input_data = HandoffInputData(
        input_history=[
            {"type": "reasoning", "id": "rs_1", "content": [{"type": "output_text", "text": "Reasoning text"}]},
            {"type": "message", "role": "assistant", "id": "msg_1", "content": "hi"},
        ],
        pre_handoff_items=(),
        new_items=(),
        run_context=None,
    )

    filtered = await handoff_tool.input_filter(input_data)
    assert all(item.get("type") != "reasoning" for item in filtered.input_history)


@pytest.mark.asyncio
async def test_handoff_preserves_reasoning_content_for_non_openai_recipient():
    recipient = Agent(name="RecipientLiteLLM", instructions="You are a helpful assistant.")
    handoff_builder = SendMessageHandoff()
    handoff_builder.add_reminder = False
    handoff_tool = handoff_builder.create_handoff(recipient)
    assert handoff_tool.input_filter is not None

    input_data = HandoffInputData(
        input_history=[
            {"type": "reasoning", "id": "rs_1", "content": [{"type": "output_text", "text": "Reasoning text"}]},
            {"type": "message", "role": "assistant", "id": "msg_1", "content": "hi"},
        ],
        pre_handoff_items=(),
        new_items=(),
        run_context=None,
    )

    filtered = await handoff_tool.input_filter(input_data)
    reasoning_items = [item for item in filtered.input_history if item.get("type") == "reasoning"]
    assert len(reasoning_items) == 1
    assert reasoning_items[0].get("content") == [{"type": "output_text", "text": "Reasoning text"}]


@pytest.mark.asyncio
async def test_handoff_normalizes_run_item_raw_ids_for_dict_tool_items():
    recipient = Agent(name="Recipient", instructions="You are a helpful assistant.")
    handoff_builder = SendMessageHandoff()
    handoff_builder.add_reminder = False
    handoff_tool = handoff_builder.create_handoff(recipient)
    assert handoff_tool.input_filter is not None

    sender = Agent(name="Sender", instructions="You are a helpful assistant.")
    tool_call = ToolCallItem(
        agent=sender,
        raw_item={
            "type": "function_call",
            "id": FAKE_RESPONSES_ID,
            "call_id": "call_1",
            "name": "noop",
            "arguments": "{}",
        },
    )
    tool_out = ToolCallOutputItem(
        agent=sender,
        raw_item={"type": "function_call_output", "call_id": "call_1", "output": "ok"},
        output="ok",
    )

    input_data = HandoffInputData(
        input_history=(),
        pre_handoff_items=(tool_call,),
        new_items=(tool_out,),
        run_context=None,
    )

    filtered = await handoff_tool.input_filter(input_data)

    assert isinstance(filtered.pre_handoff_items[0].raw_item, dict)
    assert filtered.pre_handoff_items[0].raw_item["id"] != FAKE_RESPONSES_ID
    assert filtered.pre_handoff_items[0].raw_item["id"].startswith("fc_handoff_")


@pytest.mark.asyncio
async def test_handoff_add_reminder_true_injects_system_message_and_normalizes_history_ids():
    recipient = Agent(name="Recipient", instructions="You are a helpful assistant.")
    handoff_builder = SendMessageHandoff()  # add_reminder=True by default
    handoff_tool = handoff_builder.create_handoff(recipient)
    assert handoff_tool.input_filter is not None

    thread_manager = ThreadManager()
    thread_manager.add_message({"role": "assistant", "content": "hi", "timestamp": 1, "agent": "X"})
    ctx = MasterContext(user_context={}, thread_manager=thread_manager, agents={})
    run_ctx = RunContextWrapper(context=ctx)

    input_data = HandoffInputData(
        input_history=(
            {"type": "message", "role": "assistant", "id": FAKE_RESPONSES_ID, "content": "hi"},
        ),
        pre_handoff_items=(),
        new_items=(),
        run_context=run_ctx,
    )

    filtered = await handoff_tool.input_filter(input_data)

    assert isinstance(filtered.input_history, tuple)
    assert filtered.input_history[0]["id"] != FAKE_RESPONSES_ID
    assert filtered.input_history[0]["id"].startswith("msg_")
    assert any(item.get("role") == "system" for item in filtered.input_history)


@pytest.mark.asyncio
async def test_handoff_normalizes_run_item_raw_ids_for_mcp_items_with_dict_raw_item():
    recipient = Agent(name="Recipient", instructions="You are a helpful assistant.")
    handoff_builder = SendMessageHandoff()
    handoff_builder.add_reminder = False
    handoff_tool = handoff_builder.create_handoff(recipient)
    assert handoff_tool.input_filter is not None

    sender = Agent(name="Sender", instructions="You are a helpful assistant.")
    mcp_item = MCPListToolsItem(
        agent=sender,
        raw_item={"type": "mcp_list_tools", "id": FAKE_RESPONSES_ID, "server_label": "srv", "tools": []},
    )

    input_data = HandoffInputData(
        input_history=(),
        pre_handoff_items=(mcp_item,),
        new_items=(),
        run_context=None,
    )

    filtered = await handoff_tool.input_filter(input_data)

    assert isinstance(filtered.pre_handoff_items[0].raw_item, dict)
    assert filtered.pre_handoff_items[0].raw_item["id"] != FAKE_RESPONSES_ID
    assert filtered.pre_handoff_items[0].raw_item["id"].startswith("msg_handoff_")


@pytest.mark.asyncio
async def test_handoff_input_history_tuple_is_normalized_and_preserved_as_tuple():
    recipient = Agent(name="Recipient", instructions="You are a helpful assistant.")
    handoff_builder = SendMessageHandoff()
    handoff_builder.add_reminder = False
    handoff_tool = handoff_builder.create_handoff(recipient)
    assert handoff_tool.input_filter is not None

    input_data = HandoffInputData(
        input_history=(
            {"type": "message", "role": "assistant", "id": FAKE_RESPONSES_ID, "content": "hi"},
        ),
        pre_handoff_items=(),
        new_items=(),
        run_context=None,
    )

    filtered = await handoff_tool.input_filter(input_data)
    assert isinstance(filtered.input_history, tuple)
    assert filtered.input_history[0]["id"] != FAKE_RESPONSES_ID
    assert filtered.input_history[0]["id"].startswith("msg_")


@pytest.mark.asyncio
async def test_handoff_input_history_str_with_reminder_is_wrapped_and_does_not_crash():
    recipient = Agent(name="Recipient", instructions="You are a helpful assistant.")
    handoff_builder = SendMessageHandoff()  # add_reminder=True
    handoff_tool = handoff_builder.create_handoff(recipient)
    assert handoff_tool.input_filter is not None

    thread_manager = ThreadManager()
    thread_manager.add_message({"role": "assistant", "content": "hi", "timestamp": 1, "agent": "X"})
    ctx = MasterContext(user_context={}, thread_manager=thread_manager, agents={})
    run_ctx = RunContextWrapper(context=ctx)

    input_data = HandoffInputData(
        input_history="Hello from caller",
        pre_handoff_items=(),
        new_items=(),
        run_context=run_ctx,
    )

    filtered = await handoff_tool.input_filter(input_data)
    assert isinstance(filtered.input_history, tuple)
    # First item is user-wrapped original string
    assert filtered.input_history[0]["role"] == "user"
    assert filtered.input_history[0]["content"] == "Hello from caller"
    # Reminder is injected as a system message
    assert any(item.get("role") == "system" for item in filtered.input_history)


@pytest.mark.asyncio
async def test_handoff_add_reminder_true_with_thread_manager_none_does_not_crash_and_normalizes():
    recipient = Agent(name="Recipient", instructions="You are a helpful assistant.")
    handoff_builder = SendMessageHandoff()  # add_reminder=True
    handoff_tool = handoff_builder.create_handoff(recipient)
    assert handoff_tool.input_filter is not None

    ctx = MasterContext(user_context={}, thread_manager=None, agents={})
    run_ctx = RunContextWrapper(context=ctx)

    input_data = HandoffInputData(
        input_history=(
            {"type": "message", "role": "assistant", "id": FAKE_RESPONSES_ID, "content": "hi"},
        ),
        pre_handoff_items=(),
        new_items=(),
        run_context=run_ctx,
    )

    filtered = await handoff_tool.input_filter(input_data)
    assert isinstance(filtered.input_history, tuple)
    assert filtered.input_history[0]["id"] != FAKE_RESPONSES_ID
    assert filtered.input_history[0]["id"].startswith("msg_")


@pytest.mark.asyncio
async def test_handoff_normalizes_run_item_raw_ids_for_base_model_tool_items_and_mixed_payload():
    recipient = Agent(name="Recipient", instructions="You are a helpful assistant.")
    handoff_builder = SendMessageHandoff()
    handoff_builder.add_reminder = False
    handoff_tool = handoff_builder.create_handoff(recipient)
    assert handoff_tool.input_filter is not None

    sender = Agent(name="Sender", instructions="You are a helpful assistant.")
    base_model_call = ResponseFunctionToolCall(
        type="function_call",
        id=FAKE_RESPONSES_ID,
        call_id="call_bm_1",
        name="noop",
        arguments="{}",
    )
    tool_call_model = ToolCallItem(agent=sender, raw_item=base_model_call)

    tool_call_dict = ToolCallItem(
        agent=sender,
        raw_item={
            "type": "function_call",
            "id": FAKE_RESPONSES_ID,
            "call_id": "call_dict_1",
            "name": "noop",
            "arguments": "{}",
        },
    )

    input_data = HandoffInputData(
        input_history=(),
        pre_handoff_items=(tool_call_model, tool_call_dict),
        new_items=(),
        run_context=None,
    )

    filtered = await handoff_tool.input_filter(input_data)
    # BaseModel call id rewritten (either via attribute set or model_copy replacement)
    bm_raw = filtered.pre_handoff_items[0].raw_item
    assert getattr(bm_raw, "id", None) != FAKE_RESPONSES_ID
    assert str(getattr(bm_raw, "id", "")).startswith("fc_handoff_")
    # Dict call id rewritten too
    assert isinstance(filtered.pre_handoff_items[1].raw_item, dict)
    assert filtered.pre_handoff_items[1].raw_item["id"] != FAKE_RESPONSES_ID
    assert filtered.pre_handoff_items[1].raw_item["id"].startswith("fc_handoff_")


@pytest.mark.asyncio
async def test_two_hop_handoff_openai_then_non_openai_preserves_valid_history():
    """
    Integration-style handoff test:
    - First handoff targets OpenAIResponsesModel: reasoning is dropped and IDs are normalized.
    - Second handoff targets non-OpenAI: history remains valid and IDs stay normalized.
    """
    sender = Agent(name="Sender", instructions="You are a helpful assistant.")
    recipient_openai = Agent(
        name="RecipientOpenAI",
        instructions="You are a helpful assistant.",
        model=OpenAIResponsesModel(model="gpt-5.2", openai_client=AsyncOpenAI(api_key="test-key")),
    )
    recipient_other = Agent(name="RecipientOther", instructions="You are a helpful assistant.")

    # First hop: OpenAI recipient, reminder enabled
    hop1_builder = SendMessageHandoff()
    hop1_builder.add_reminder = True
    hop1 = hop1_builder.create_handoff(recipient_openai)
    assert hop1.input_filter is not None

    thread_manager = ThreadManager()
    thread_manager.add_message({"role": "assistant", "content": "seed", "timestamp": 1, "agent": "X"})
    ctx = MasterContext(user_context={}, thread_manager=thread_manager, agents={})
    run_ctx = RunContextWrapper(context=ctx)

    # Mix reasoning + placeholder ids in history; include a tool call RunItem as BaseModel.
    base_model_call = ResponseFunctionToolCall(
        type="function_call",
        id=FAKE_RESPONSES_ID,
        call_id="call_hop_1",
        name="noop",
        arguments="{}",
    )
    run_item = ToolCallItem(agent=sender, raw_item=base_model_call)

    input_data = HandoffInputData(
        input_history=[
            {"type": "reasoning", "id": "rs_1", "content": [{"type": "output_text", "text": "Reasoning text"}]},
            {"type": "message", "role": "assistant", "id": FAKE_RESPONSES_ID, "content": "hi"},
        ],
        pre_handoff_items=(run_item,),
        new_items=(),
        run_context=run_ctx,
    )

    hop1_out = await hop1.input_filter(input_data)
    assert isinstance(hop1_out.input_history, tuple)
    assert all(item.get("type") != "reasoning" for item in hop1_out.input_history)
    assert any(item.get("role") == "system" for item in hop1_out.input_history)
    # Reasoning is dropped for OpenAI recipients; remaining message ids are normalized.
    assert hop1_out.input_history[0].get("id") != FAKE_RESPONSES_ID
    assert hop1_out.input_history[0].get("id", "").startswith("msg_")
    assert getattr(hop1_out.pre_handoff_items[0].raw_item, "id", None) != FAKE_RESPONSES_ID

    # Second hop: non-OpenAI recipient, reminder enabled, should not crash and should keep ids stable.
    hop2_builder = SendMessageHandoff()
    hop2_builder.add_reminder = True
    hop2 = hop2_builder.create_handoff(recipient_other)
    assert hop2.input_filter is not None

    hop2_in = HandoffInputData(
        input_history=hop1_out.input_history,
        pre_handoff_items=hop1_out.pre_handoff_items,
        new_items=hop1_out.new_items,
        run_context=run_ctx,
    )
    hop2_out = await hop2.input_filter(hop2_in)
    assert isinstance(hop2_out.input_history, tuple)
    assert all(item.get("id") != FAKE_RESPONSES_ID for item in hop2_out.input_history if "id" in item)


@pytest.mark.asyncio
async def test_handoff_orphan_function_call_is_not_auto_cleaned():
    """Document current behavior: handoff normalization does not remove orphan tool calls."""
    recipient_openai = Agent(
        name="RecipientOpenAI",
        instructions="You are a helpful assistant.",
        model=OpenAIResponsesModel(model="gpt-5.2", openai_client=AsyncOpenAI(api_key="test-key")),
    )
    handoff_builder = SendMessageHandoff()
    handoff_builder.add_reminder = False
    handoff_tool = handoff_builder.create_handoff(recipient_openai)
    assert handoff_tool.input_filter is not None

    input_data = HandoffInputData(
        input_history=(
            {
                "type": "function_call",
                "id": FAKE_RESPONSES_ID,
                "call_id": "call_orphan_1",
                "name": "noop",
                "arguments": "{}",
            },
        ),
        pre_handoff_items=(),
        new_items=(),
        run_context=None,
    )

    filtered = await handoff_tool.input_filter(input_data)
    assert isinstance(filtered.input_history, tuple)
    # The orphan tool call remains (we do not remove orphans here).
    assert filtered.input_history[0]["type"] == "function_call"
    # Its placeholder id is normalized.
    assert filtered.input_history[0]["id"] != FAKE_RESPONSES_ID
    # Normalizer prefers a valid call_id for function_call items.
    assert filtered.input_history[0]["id"] == "call_orphan_1"


@pytest.mark.asyncio
async def test_handoff_normalizes_mcp_run_item_base_model_raw_item():
    recipient = Agent(name="Recipient", instructions="You are a helpful assistant.")
    handoff_builder = SendMessageHandoff()
    handoff_builder.add_reminder = False
    handoff_tool = handoff_builder.create_handoff(recipient)
    assert handoff_tool.input_filter is not None

    sender = Agent(name="Sender", instructions="You are a helpful assistant.")
    mcp_base = McpListTools(type="mcp_list_tools", id=FAKE_RESPONSES_ID, server_label="srv", tools=[])
    run_item = MCPListToolsItem(agent=sender, raw_item=mcp_base)

    input_data = HandoffInputData(
        input_history=(),
        pre_handoff_items=(run_item,),
        new_items=(),
        run_context=None,
    )

    filtered = await handoff_tool.input_filter(input_data)
    raw = filtered.pre_handoff_items[0].raw_item
    assert getattr(raw, "id", None) != FAKE_RESPONSES_ID
    assert str(getattr(raw, "id", "")).startswith("msg_handoff_")


@pytest.mark.asyncio
async def test_handoff_unknown_item_type_passthrough_and_normalizes_placeholder_id():
    recipient = Agent(name="Recipient", instructions="You are a helpful assistant.")
    handoff_builder = SendMessageHandoff()
    handoff_builder.add_reminder = False
    handoff_tool = handoff_builder.create_handoff(recipient)
    assert handoff_tool.input_filter is not None

    input_data = HandoffInputData(
        input_history=(
            {"type": "unknown_future_item", "id": FAKE_RESPONSES_ID, "payload": {"x": 1}},
        ),
        pre_handoff_items=(),
        new_items=(),
        run_context=None,
    )

    filtered = await handoff_tool.input_filter(input_data)
    assert filtered.input_history[0]["type"] == "unknown_future_item"
    assert filtered.input_history[0]["id"] != FAKE_RESPONSES_ID


"""Tests for AgencySession: the SDK Session adapter over the shared flat store."""

from typing import Any

import pytest
from agents import TResponseInputItem

from agency_swarm import Agency, Agent, ThreadManager
from agency_swarm.agent.agency_session import create_agency_session
from agency_swarm.agent.context_types import AgencyContext
from agency_swarm.messages import MessageFormatter
from tests.deterministic_model import DeterministicModel


def _make_session(
    agent_name: str = "MainAgent",
    sender_name: str | None = None,
    new_input: list[TResponseInputItem] | None = None,
    thread_manager: ThreadManager | None = None,
    agency_context: AgencyContext | None = None,
):
    agent = Agent(name=agent_name, instructions="test", model=DeterministicModel())
    context = agency_context or AgencyContext(
        agency_instance=None, thread_manager=thread_manager or ThreadManager(), subagents={}
    )
    return create_agency_session(
        agent=agent,
        sender_name=sender_name,
        agency_context=context,
        new_input_items=new_input or [],
        agent_run_id="agent_run_1",
        parent_run_id=None,
        run_trace_id="trace_1",
        run_config_override=None,
    )


def _user_item(text: str) -> TResponseInputItem:
    return {"role": "user", "content": text}  # type: ignore[return-value]


def _assistant_item(text: str) -> TResponseInputItem:
    return {"role": "assistant", "content": [{"type": "output_text", "text": text}]}  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_add_items_enriches_metadata_and_get_items_strips_it() -> None:
    session = _make_session(new_input=[_user_item("hi")])
    # Input is persisted at creation but stays pending until the first
    # session_input_callback consume, exactly like a real SDK run.
    stored = session._thread_manager.get_all_messages()
    assert len(stored) == 1
    assert stored[0]["callerAgent"] is None

    callback = session.session_input_callback()
    merged = callback(await session.get_items(), [_user_item("hi")])
    assert len(merged) == 1  # pending input appended once as new

    await session.add_items([_assistant_item("hello")])
    stored = session._thread_manager.get_all_messages()
    assert len(stored) == 2
    for message in stored:
        assert message["agent"] == "MainAgent"
        assert message["callerAgent"] is None
        assert message["agent_run_id"] == "agent_run_1"
        assert message["run_trace_id"] == "trace_1"
        assert message["history_protocol"] == MessageFormatter.HISTORY_PROTOCOL_RESPONSES

    items = await session.get_items()
    assert len(items) == 2
    for item in items:
        for field in MessageFormatter.metadata_fields:
            assert field not in item


@pytest.mark.asyncio
async def test_shared_store_visibility_across_agents() -> None:
    thread_manager = ThreadManager()
    context = AgencyContext(agency_instance=None, thread_manager=thread_manager, subagents={})
    user_session = _make_session(thread_manager=thread_manager, agency_context=context)
    pair_session = _make_session(sender_name="HelperAgent", thread_manager=thread_manager, agency_context=context)

    await user_session.add_items([_user_item("user msg")])
    await pair_session.add_items([_assistant_item("pair reply")])

    user_items = await user_session.get_items()
    # User thread sees shared (callerAgent=None) messages but not agent-to-agent ones.
    assert [item.get("content") for item in user_items] == ["user msg"]
    pair_items = await pair_session.get_items()
    # Pair slice sees the bidirectional exchange, not the user thread.
    assert len(pair_items) == 1


@pytest.mark.asyncio
async def test_pop_item_and_clear_session_scope_to_slice() -> None:
    thread_manager = ThreadManager()
    context = AgencyContext(agency_instance=None, thread_manager=thread_manager, subagents={})
    session = _make_session(thread_manager=thread_manager, agency_context=context)
    pair_session = _make_session(sender_name="HelperAgent", thread_manager=thread_manager, agency_context=context)

    await session.add_items([_user_item("u1"), _assistant_item("a1")])
    await pair_session.add_items([_user_item("pair q")])

    popped = await session.pop_item()
    assert popped is not None
    assert "agent" not in popped
    assert len(thread_manager.get_all_messages()) == 2

    await session.clear_session()
    remaining = thread_manager.get_all_messages()
    assert len(remaining) == 1
    assert remaining[0]["callerAgent"] == "HelperAgent"


@pytest.mark.asyncio
async def test_ephemeral_parts_never_persist() -> None:
    raw_input: TResponseInputItem = {
        "role": "user",
        "content": [
            {"type": "input_text", "text": "real question"},
            {"type": "input_text", "text": "one-shot note", "_agency_swarm_ephemeral": True},
        ],
    }  # type: ignore[assignment]
    session = _make_session(new_input=[raw_input])

    # The SDK persists whatever the callback returned (the model-facing form);
    # the session must still store the raw item minus ephemeral parts.
    await session.add_items(session.model_new_items)
    stored = session._thread_manager.get_all_messages()
    assert len(stored) == 1
    content = stored[0]["content"]
    assert [part["text"] for part in content] == ["real question"]

    # Model view keeps the ephemeral part, marker stripped.
    model_content = session.model_new_items[0]["content"]
    assert len(model_content) == 2
    assert "_agency_swarm_ephemeral" not in model_content[1]


@pytest.mark.asyncio
async def test_repeated_saves_dedupe() -> None:
    session = _make_session()
    item = _assistant_item("same reply")
    await session.add_items([item])
    await session.add_items([item])
    assert len(session._thread_manager.get_all_messages()) == 1


@pytest.mark.asyncio
async def test_session_input_callback_merges_sanitized_new_items() -> None:
    session = _make_session(new_input=[_user_item("new question")])
    callback = session.session_input_callback()
    history: list[TResponseInputItem] = [_user_item("earlier")]
    merged = callback(history, [_user_item("raw new")])
    assert [item.get("content") for item in merged] == ["earlier", "new question"]


@pytest.mark.asyncio
async def test_get_response_round_trip_through_sdk_session() -> None:
    """A real Runner run persists via the session; the next run replays it."""
    saved_snapshots: list[list[dict[str, Any]]] = []
    agent = Agent(
        name="RecallAgent",
        instructions="test",
        model=DeterministicModel(),
    )
    agency = Agency(
        agent,
        load_threads_callback=lambda: [],
        save_threads_callback=lambda messages: saved_snapshots.append([dict(m) for m in messages]),
    )

    first = await agency.get_response("remember secret code: zebra-7", "RecallAgent")
    assert "REMEMBERED" in str(first.final_output)

    stored = agency.thread_manager.get_all_messages()
    assert [m["role"] for m in stored] == ["user", "assistant"]
    assert all(m["callerAgent"] is None for m in stored)

    second = await agency.get_response("recall the secret", "RecallAgent")
    assert "zebra-7" in str(second.final_output)
    assert [m["role"] for m in agency.thread_manager.get_all_messages()] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert saved_snapshots, "save callback must fire through the session persistence path"


@pytest.mark.asyncio
async def test_send_message_mid_tool_call_writes_shared_store() -> None:
    """A nested agent-to-agent run must see and extend the same flat store."""
    caller = Agent(name="CallerAgent", instructions="test", model=DeterministicModel())
    responder = Agent(name="ResponderAgent", instructions="test", model=DeterministicModel())
    agency = Agency(caller, communication_flows=[(caller, responder)])

    result = await agency.get_response("send a message to ResponderAgent message: hello pair", "CallerAgent")
    assert result.final_output is not None

    stored = agency.thread_manager.get_all_messages()
    pair_messages = [m for m in stored if m.get("callerAgent") == "CallerAgent"]
    assert pair_messages, "nested run must persist pair-scoped messages into the shared store"
    assert any(m.get("agent") == "ResponderAgent" for m in pair_messages)

"""Unit tests for streaming run-id tracking and final persistence replacement."""

from __future__ import annotations

from types import SimpleNamespace

from agents import Agent as SDKAgent
from agents.items import MessageOutputItem
from agents.stream_events import AgentUpdatedStreamEvent
from openai.types.responses import ResponseOutputMessage, ResponseOutputText

from agency_swarm import Agent
from agency_swarm.agent.core import AgencyContext
from agency_swarm.agent.execution_stream_persistence import (
    StreamMetadataStore,
    _persist_streamed_items,
    _update_names_from_event,
)
from agency_swarm.context import MasterContext
from agency_swarm.messages import MessageFormatter
from agency_swarm.utils.thread import ThreadManager


def test_update_names_from_event_preserves_initial_run_id_and_updates_on_switch() -> None:
    """Initial AgentUpdatedStreamEvent keeps the run ID; agent switches or explicit IDs update it."""
    agent_a = SDKAgent(name="AgentA", instructions="a")
    agent_b = SDKAgent(name="AgentB", instructions="b")
    master_context = MasterContext(thread_manager=ThreadManager(), agents={})
    master_context._current_agent_run_id = "agent_run_initial"

    name, run_id = _update_names_from_event(
        AgentUpdatedStreamEvent(new_agent=agent_a),
        "AgentA",
        "agent_run_initial",
        master_context,
    )
    assert (name, run_id) == ("AgentA", "agent_run_initial")
    assert master_context._current_agent_run_id == "agent_run_initial"

    name, switched_run_id = _update_names_from_event(
        AgentUpdatedStreamEvent(new_agent=agent_b),
        name,
        run_id,
        master_context,
    )
    assert name == "AgentB"
    assert switched_run_id != "agent_run_initial"
    assert master_context._current_agent_run_id == switched_run_id

    name, same_after_switch = _update_names_from_event(
        AgentUpdatedStreamEvent(new_agent=agent_b),
        name,
        switched_run_id,
        master_context,
    )
    assert (name, same_after_switch) == ("AgentB", switched_run_id)

    explicit_event = SimpleNamespace(type="agent_updated_stream_event", new_agent=agent_b, id="custom_run_id")
    name, explicit_run_id = _update_names_from_event(explicit_event, name, same_after_switch, master_context)
    assert (name, explicit_run_id) == ("AgentB", "custom_run_id")
    assert master_context._current_agent_run_id == "custom_run_id"


def test_persist_streamed_items_replaces_session_copy_and_keeps_handoff_reminder() -> None:
    """Final persistence replaces session-written copies while preserving untyped handoff reminders."""
    thread_manager = ThreadManager()
    user_msg = {
        "type": "message",
        "role": "user",
        "content": "hello",
        "agent": "AgentA",
        "callerAgent": None,
        "agent_run_id": "run_session",
        "history_protocol": MessageFormatter.HISTORY_PROTOCOL_RESPONSES,
    }
    handoff_reminder = {
        "role": "system",
        "content": "Transfer completed. You are AgentB. Please continue the task.",
        "message_origin": "handoff_reminder",
        "agent": "AgentA",
        "callerAgent": None,
        "agent_run_id": "run_session",
        "history_protocol": MessageFormatter.HISTORY_PROTOCOL_RESPONSES,
    }
    session_copy = {
        "type": "message",
        "id": "msg_run_session_0",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "from B", "annotations": []}],
        "agent": "AgentB",
        "callerAgent": None,
        "agent_run_id": "run_session",
        "history_protocol": MessageFormatter.HISTORY_PROTOCOL_RESPONSES,
    }
    thread_manager.add_messages([user_msg, handoff_reminder, session_copy])  # type: ignore[list-item]

    agent_a = Agent(name="AgentA", instructions="a")
    agent_b = Agent(name="AgentB", instructions="b")
    final_item = MessageOutputItem(
        agent=agent_b,
        raw_item=ResponseOutputMessage(
            id="msg_run_handoff_0",
            role="assistant",
            status="completed",
            type="message",
            content=[ResponseOutputText(type="output_text", text="from B", annotations=[])],
        ),
    )

    _persist_streamed_items(
        streaming_result=SimpleNamespace(new_items=[final_item]),
        metadata_store=StreamMetadataStore(by_item={id(final_item): ("AgentB", "run_handoff", None, 2)}),
        collected_items=[final_item],
        agent=agent_a,
        sender_name=None,
        parent_run_id=None,
        run_trace_id="trace_1",
        fallback_agent_run_id="run_handoff",
        session_agent_run_id="run_session",
        agency_context=AgencyContext(agency_instance=None, thread_manager=thread_manager),
        initial_saved_count=0,
    )

    stored = thread_manager.get_all_messages()
    assert [msg.get("role") for msg in stored] == ["user", "system", "assistant"]
    assert stored[1].get("message_origin") == "handoff_reminder"
    assert stored[2].get("id") == "msg_run_handoff_0"
    assert stored[2].get("agent") == "AgentB"

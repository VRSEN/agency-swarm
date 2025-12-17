"""Regression tests for LiteLLM/Chat Completions placeholder IDs in stream persistence.

These tests verify that the Python object id() based matching works correctly
with LiteLLM's placeholder IDs (FAKE_RESPONSES_ID).
"""

from unittest.mock import patch

from agents.items import ToolCallItem
from agents.models.fake_id import FAKE_RESPONSES_ID
from openai.types.responses import ResponseFunctionToolCall

from agency_swarm import Agent
from agency_swarm.agent.core import AgencyContext
from agency_swarm.agent.execution_stream_persistence import (
    StreamMetadataStore,
    _compute_content_hash,
    _persist_streamed_items,
)


class _DummyThreadManager:
    def __init__(self, messages: list[dict] | None = None) -> None:
        self._messages: list[dict] = list(messages or [])

    def get_all_messages(self) -> list[dict]:
        return list(self._messages)

    def replace_messages(self, messages: list[dict]) -> None:
        self._messages = list(messages)

    def persist(self) -> None:  # pragma: no cover - side-effect boundary
        return


class _DummyStreamResult:
    def __init__(self, new_items: list, input_list: list[dict] | None = None) -> None:
        self.new_items = new_items
        self._input_list = input_list if input_list is not None else [item.to_input_item() for item in new_items]

    def to_input_list(self) -> list[dict]:
        return list(self._input_list)


@patch(
    "agency_swarm.agent.execution_stream_persistence.MessageFilter.remove_orphaned_messages",
    side_effect=lambda x: x,
)
@patch("agency_swarm.agent.execution_stream_persistence.MessageFilter.should_filter", return_value=False)
@patch("agency_swarm.agent.execution_stream_persistence.MessageFormatter.extract_hosted_tool_results", return_value=[])
def test_persist_streamed_items_maps_by_python_object_id_with_fake_ids(mock_extract, mock_filter, mock_orphan) -> None:
    """Distinct tool calls sharing FAKE_RESPONSES_ID are correctly matched via Python object id()."""
    agent_a = Agent(name="AgentA", instructions="noop")
    agent_b = Agent(name="AgentB", instructions="noop")

    tool_call_a = ResponseFunctionToolCall(
        arguments="{}",
        call_id="call_a",
        name="tool_a",
        type="function_call",
        id=FAKE_RESPONSES_ID,
        status="in_progress",
    )
    tool_call_b = ResponseFunctionToolCall(
        arguments="{}",
        call_id="call_b",
        name="tool_b",
        type="function_call",
        id=FAKE_RESPONSES_ID,
        status="in_progress",
    )

    tool_item_a = ToolCallItem(agent=agent_a, raw_item=tool_call_a)
    tool_item_b = ToolCallItem(agent=agent_b, raw_item=tool_call_b)

    # Metadata tracked by Python object id() during streaming
    # 4-tuple: (agent_name, agent_run_id, caller_name, timestamp)
    metadata_store = StreamMetadataStore(
        by_item={
            id(tool_item_a): (agent_a.name, "agent_run_a", None, 1000000),
            id(tool_item_b): (agent_b.name, "agent_run_b", None, 2000000),
        }
    )

    thread_manager = _DummyThreadManager()
    agency_context = AgencyContext(agency_instance=None, thread_manager=thread_manager)

    _persist_streamed_items(
        streaming_result=_DummyStreamResult([tool_item_a, tool_item_b]),
        metadata_store=metadata_store,
        collected_items=[tool_item_a, tool_item_b],
        agent=Agent(name="Runner", instructions="noop"),
        sender_name="Manager",
        parent_run_id=None,
        run_trace_id="trace",
        fallback_agent_run_id="agent_run_runner",
        agency_context=agency_context,
        initial_saved_count=0,
    )

    persisted = thread_manager.get_all_messages()
    by_call_id = {m.get("call_id"): m for m in persisted if isinstance(m, dict)}

    assert by_call_id["call_a"]["agent"] == "AgentA"
    assert by_call_id["call_a"]["agent_run_id"] == "agent_run_a"
    assert by_call_id["call_b"]["agent"] == "AgentB"
    assert by_call_id["call_b"]["agent_run_id"] == "agent_run_b"


def test_persist_streamed_items_does_not_drop_unrelated_placeholder_id_items() -> None:
    """Replacing one placeholder-id item must not delete all other placeholder-id items."""
    existing = [
        {"id": FAKE_RESPONSES_ID, "type": "function_call", "call_id": "call_a", "agent_run_id": "run_a"},
        {
            "id": FAKE_RESPONSES_ID,
            "type": "function_call_output",
            "call_id": "call_a",
            "output": "old",
            "agent_run_id": "run_a",
        },
        {"id": FAKE_RESPONSES_ID, "type": "function_call", "call_id": "call_b", "agent_run_id": "run_b_old"},
        {
            "id": FAKE_RESPONSES_ID,
            "type": "function_call_output",
            "call_id": "call_b",
            "output": "old",
            "agent_run_id": "run_b_old",
        },
    ]

    thread_manager = _DummyThreadManager(messages=existing)
    agency_context = AgencyContext(agency_instance=None, thread_manager=thread_manager)

    # Create a ToolCallItem and ToolCallOutputItem for call_b update
    agent = Agent(name="Runner", instructions="noop")
    tool_call_b = ResponseFunctionToolCall(
        arguments="{}",
        call_id="call_b",
        name="tool_b",
        type="function_call",
        id=FAKE_RESPONSES_ID,
        status="in_progress",
    )
    tool_item_b = ToolCallItem(agent=agent, raw_item=tool_call_b)
    # Note: ToolCallOutputItem requires specific raw_item structure, use a simple mock

    class MockToolOutputItem:
        def __init__(self):
            self.type = "tool_call_output_item"

        def to_input_item(self):
            return {"id": FAKE_RESPONSES_ID, "type": "function_call_output", "call_id": "call_b", "output": "new"}

    tool_output_b = MockToolOutputItem()

    _persist_streamed_items(
        streaming_result=_DummyStreamResult([tool_item_b, tool_output_b]),
        metadata_store=StreamMetadataStore(),  # No metadata tracked - use fallback
        collected_items=[],
        agent=agent,
        sender_name="Manager",
        parent_run_id=None,
        run_trace_id="trace",
        fallback_agent_run_id="agent_run_runner",
        agency_context=agency_context,
        initial_saved_count=0,
    )

    persisted = thread_manager.get_all_messages()
    call_ids = [(m.get("call_id"), m.get("type")) for m in persisted]

    assert ("call_a", "function_call") in call_ids
    assert ("call_a", "function_call_output") in call_ids
    assert ("call_b", "function_call") in call_ids
    assert ("call_b", "function_call_output") in call_ids


@patch(
    "agency_swarm.agent.execution_stream_persistence.MessageFilter.remove_orphaned_messages",
    side_effect=lambda x: x,
)
@patch("agency_swarm.agent.execution_stream_persistence.MessageFilter.should_filter", return_value=False)
@patch("agency_swarm.agent.execution_stream_persistence.MessageFormatter.extract_hosted_tool_results", return_value=[])
def test_persist_streamed_items_hash_collision_is_fifo(mock_extract, mock_filter, mock_orphan) -> None:
    """Hash-based fallback matching consumes metadata FIFO to avoid collisions overwriting prior items."""

    class _RawItem:
        def __init__(self, output: str) -> None:
            self.output = output

    class _HashOnlyItem:
        def __init__(self, item_type: str, output: str) -> None:
            self.type = item_type
            self.id = FAKE_RESPONSES_ID
            self.call_id = None
            self.raw_item = _RawItem(output)

        def to_input_item(self) -> dict:
            return {"id": self.id, "type": self.type, "output": self.raw_item.output}

    item_type = "handoff_output_item"
    run_item_1 = _HashOnlyItem(item_type=item_type, output="same")
    run_item_2 = _HashOnlyItem(item_type=item_type, output="same")

    content_hash = _compute_content_hash(run_item_1)
    assert isinstance(content_hash, str)

    metadata_store = StreamMetadataStore(
        hash_queues={
            (content_hash, item_type): [
                ("Agent1", "run_1", "Caller1", 1000000),
                ("Agent2", "run_2", "Caller2", 2000000),
            ]
        }
    )

    thread_manager = _DummyThreadManager()
    agency_context = AgencyContext(agency_instance=None, thread_manager=thread_manager)

    _persist_streamed_items(
        streaming_result=_DummyStreamResult([run_item_1, run_item_2]),
        metadata_store=metadata_store,
        collected_items=[],
        agent=Agent(name="Runner", instructions="noop"),
        sender_name="Manager",
        parent_run_id=None,
        run_trace_id="trace",
        fallback_agent_run_id="agent_run_runner",
        agency_context=agency_context,
        initial_saved_count=0,
    )

    persisted = thread_manager.get_all_messages()

    assert persisted[0]["agent"] == "Agent1"
    assert persisted[0]["agent_run_id"] == "run_1"
    assert persisted[0]["callerAgent"] == "Caller1"
    assert persisted[1]["agent"] == "Agent2"
    assert persisted[1]["agent_run_id"] == "run_2"
    assert persisted[1]["callerAgent"] == "Caller2"

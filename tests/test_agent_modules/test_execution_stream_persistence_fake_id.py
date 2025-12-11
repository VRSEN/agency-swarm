"""Regression tests for LiteLLM/Chat Completions placeholder IDs in stream persistence."""

from agents.items import ToolCallItem
from agents.models.fake_id import FAKE_RESPONSES_ID
from openai.types.responses import ResponseFunctionToolCall

from agency_swarm import Agent
from agency_swarm.agent.core import AgencyContext
from agency_swarm.agent.execution_streaming import _persist_streamed_items


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
    def __init__(self, input_list: list[dict]) -> None:
        self._input_list = list(input_list)

    def to_input_list(self) -> list[dict]:
        return list(self._input_list)


def test_persist_streamed_items_maps_placeholder_ids_by_call_id() -> None:
    """Distinct tool calls sharing FAKE_RESPONSES_ID must not collide during persistence mapping."""
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

    # Order matters: reversed(persistence_candidates) would otherwise map both items to AgentB.
    persistence_candidates = [
        (ToolCallItem(agent=agent_a, raw_item=tool_call_a), agent_a.name, "agent_run_a", None),
        (ToolCallItem(agent=agent_b, raw_item=tool_call_b), agent_b.name, "agent_run_b", None),
    ]

    stream_items = [
        {"id": FAKE_RESPONSES_ID, "type": "function_call", "call_id": "call_a"},
        {"id": FAKE_RESPONSES_ID, "type": "function_call_output", "call_id": "call_a", "output": "ok"},
        {"id": FAKE_RESPONSES_ID, "type": "function_call", "call_id": "call_b"},
        {"id": FAKE_RESPONSES_ID, "type": "function_call_output", "call_id": "call_b", "output": "ok"},
    ]

    thread_manager = _DummyThreadManager()
    agency_context = AgencyContext(agency_instance=None, thread_manager=thread_manager)

    _persist_streamed_items(
        streaming_result=_DummyStreamResult(stream_items),
        history_for_runner=[],
        persistence_candidates=persistence_candidates,
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
    by_call_and_type = {(m.get("call_id"), m.get("type")): m for m in persisted if isinstance(m, dict)}

    assert by_call_and_type[("call_a", "function_call")]["agent"] == "AgentA"
    assert by_call_and_type[("call_a", "function_call")]["agent_run_id"] == "agent_run_a"
    assert by_call_and_type[("call_b", "function_call")]["agent"] == "AgentB"
    assert by_call_and_type[("call_b", "function_call")]["agent_run_id"] == "agent_run_b"


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

    updated_items = [
        {"id": FAKE_RESPONSES_ID, "type": "function_call", "call_id": "call_b"},
        {"id": FAKE_RESPONSES_ID, "type": "function_call_output", "call_id": "call_b", "output": "new"},
    ]

    _persist_streamed_items(
        streaming_result=_DummyStreamResult(updated_items),
        history_for_runner=[],
        persistence_candidates=[],
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
    call_ids = [(m.get("call_id"), m.get("type")) for m in persisted]

    assert ("call_a", "function_call") in call_ids
    assert ("call_a", "function_call_output") in call_ids
    assert ("call_b", "function_call") in call_ids
    assert ("call_b", "function_call_output") in call_ids

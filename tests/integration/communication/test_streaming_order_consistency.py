"""
Deterministic streaming order test with two agents and custom tools.
"""

import logging
import os
from typing import Any

import pytest
from agents import ModelSettings, function_tool
from agents.models.fake_id import FAKE_RESPONSES_ID

from agency_swarm import Agency, Agent

logger = logging.getLogger(__name__)


def _assert_sanitized_history(messages: list[dict[str, Any]]) -> None:
    """Validate persisted conversation order matches sanitized tool semantics."""

    seen_ids: set[str] = set()

    for index, message in enumerate(messages):
        msg_type = message.get("type")
        msg_id = message.get("id")
        if isinstance(msg_id, str) and msg_id and msg_id != FAKE_RESPONSES_ID:
            assert msg_id not in seen_ids, f"Duplicate message id detected: {msg_id}"
            seen_ids.add(msg_id)

        if msg_type != "function_call":
            continue

        call_id = message.get("call_id")
        assert isinstance(call_id, str) and call_id, f"Missing call_id for function_call at index {index}"

        output_index = None
        for candidate in range(index + 1, len(messages)):
            if (
                messages[candidate].get("type") == "function_call_output"
                and messages[candidate].get("call_id") == call_id
            ):
                output_index = candidate
                break

        assert output_index is not None, f"No function_call_output found for call_id {call_id}"

        between = messages[index + 1 : output_index]
        assistants = [m for m in between if m.get("role") == "assistant"]
        assert not assistants, (
            f"Intermediate assistant message found between function_call and output for call_id {call_id}: {assistants}"
        )


# Additional tools for complex scenarios
@function_tool
def process_data(data: str) -> str:
    return f"PROCESSED:{data}"


@function_tool
def validate_result(result: str) -> str:
    return f"VALID:{result}"


@function_tool
def combine_results(results: str) -> str:
    return f"COMBINED:{results}"


# Hardcoded expected flow (normalized stream type, agent, tool_name)
#
# Starting with openai-agents 0.2.10, tool calls are emitted as soon as the
# model finalizes the tool call item (via ResponseOutputItemDoneEvent), so the
# semantic `tool_call_item` arrives before the agent's own message output.
# Preserve the deterministic order we now observe so that the tests confirm the
# integration keeps step with SDK streaming semantics.
EXPECTED_FLOW_DEFAULT: list[tuple[str, str, str | None]] = [
    ("tool_call_item", "MainAgent", "get_market_data"),
    ("message_output_item", "MainAgent", None),
    ("tool_call_output_item", "MainAgent", None),
    ("tool_call_item", "MainAgent", "send_message"),
    ("tool_call_item", "SubAgent", "analyze_risk"),
    ("tool_call_output_item", "SubAgent", None),
    ("message_output_item", "SubAgent", None),
    ("tool_call_output_item", "MainAgent", None),
    ("message_output_item", "MainAgent", None),
]

ANTHROPIC_MODEL_NAME = "anthropic/claude-sonnet-4-20250514"

EXPECTED_FLOW_ANTHROPIC: list[tuple[str, str, str | None]] = [
    ("tool_call_item", "MainAgent", "get_market_data"),
    ("message_output_item", "MainAgent", None),
    ("tool_call_output_item", "MainAgent", None),
    ("tool_call_item", "MainAgent", "send_message"),
    ("tool_call_item", "SubAgent", "analyze_risk"),
    ("message_output_item", "SubAgent", None),
    ("tool_call_output_item", "SubAgent", None),
    ("message_output_item", "SubAgent", None),
    ("message_output_item", "MainAgent", None),
    ("tool_call_output_item", "MainAgent", None),
    ("message_output_item", "MainAgent", None),
]


@function_tool
def get_market_data(symbol: str) -> str:
    return "AAPL:PRICE=150"


@function_tool
def analyze_risk(data: str) -> str:
    return "RISK=LOW"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("use_anthropic", "expected_flow"),
    [
        (False, EXPECTED_FLOW_DEFAULT),
        pytest.param(
            True,
            EXPECTED_FLOW_ANTHROPIC,
            marks=pytest.mark.skipif(
                not os.getenv("ANTHROPIC_API_KEY"),
                reason="ANTHROPIC_API_KEY required for Anthropic test",
            ),
        ),
    ],
)
async def test_full_streaming_flow_hardcoded_sequence(
    use_anthropic: bool, expected_flow: list[tuple[str, str, str | None]]
) -> None:
    """Proves canonical streaming order for Main→Sub agent with tool calls is deterministic."""
    if use_anthropic:
        import litellm
        from agents.extensions.models.litellm_model import LitellmModel

        litellm.modify_params = True

        main_model = LitellmModel(model=ANTHROPIC_MODEL_NAME)
        helper_model = LitellmModel(model=ANTHROPIC_MODEL_NAME)
    else:
        main_model = None
        helper_model = None

    main = Agent(
        name="MainAgent",
        description="Coordinator",
        instructions=(
            "First say 'ACK'. Then call get_market_data('AAPL'). "
            "Then use the send_message tool to ask SubAgent to analyze the data and reply. "
            "Finally, respond to the user with a brief conclusion."
        ),
        model=main_model,
        model_settings=ModelSettings(temperature=0.0),
        tools=[get_market_data],
    )

    helper = Agent(
        name="SubAgent",
        description="Risk analyzer",
        instructions=("When prompted by MainAgent: call analyze_risk on the provided data, then reply succinctly."),
        model=helper_model,
        model_settings=ModelSettings(temperature=0.0),
        tools=[analyze_risk],
    )

    agency = Agency(
        main,
        communication_flows=[main > helper],
        shared_instructions="",
    )

    before = len(agency.thread_manager.get_all_messages())

    # Collect stream as (type, agent, tool_name)
    stream_items: list[tuple[str, str, str | None]] = []
    async for event in agency.get_response_stream(message="Start."):
        if hasattr(event, "item") and event.item is not None:
            item = event.item
            evt_type = getattr(item, "type", None)
            agent_name = getattr(event, "agent", None)
            tool_name = None
            if evt_type == "tool_call_item":
                raw = getattr(item, "raw_item", None)
                tool_name = getattr(raw, "name", None)
            if isinstance(evt_type, str) and isinstance(agent_name, str):
                stream_items.append((evt_type, agent_name, tool_name))

    all_messages = agency.thread_manager.get_all_messages()
    new_messages = all_messages[before:]

    # Map saved messages to same triple format
    comparable: list[dict[str, Any]] = []
    for m in new_messages:
        t = m.get("type")
        role = m.get("role")
        if t in {"function_call", "function_call_output"} or role == "assistant":
            comparable.append(m)

    assert stream_items == expected_flow, f"Stream flow mismatch:\n got={stream_items}\n exp={expected_flow}"

    _assert_sanitized_history(comparable)


# Expected flow for multiple sequential sub-agent calls
EXPECTED_FLOW_MULTIPLE_CALLS: list[tuple[str, str, str | None]] = [
    # Agent calls tool immediately without ACK message
    ("tool_call_item", "Coordinator", "get_market_data"),  # First data fetch
    ("tool_call_output_item", "Coordinator", None),
    # First sub-agent call - SDK emits send_message immediately
    ("tool_call_item", "Coordinator", "send_message"),  # SDK emits send_message immediately
    ("tool_call_item", "Worker", "process_data"),  # Worker processes
    ("tool_call_output_item", "Worker", None),
    ("message_output_item", "Worker", None),  # Worker responds
    ("tool_call_output_item", "Coordinator", None),  # send_message completes
    # Second sub-agent call - SDK emits send_message immediately
    ("tool_call_item", "Coordinator", "send_message"),  # SDK emits send_message immediately
    ("tool_call_item", "Worker", "validate_result"),  # Worker validates
    ("tool_call_output_item", "Worker", None),
    ("message_output_item", "Worker", None),  # Worker responds again
    ("tool_call_output_item", "Coordinator", None),  # send_message completes
    ("message_output_item", "Coordinator", None),  # Final response
]


@pytest.mark.asyncio
async def test_multiple_sequential_subagent_calls() -> None:
    """Proves repeated send_message to same sub-agent streams in strict canonical order."""
    coordinator = Agent(
        name="Coordinator",
        description="Main coordinator",
        instructions=(
            "First say 'ACK'. Then call get_market_data('TEST'). "
            "Then use send_message to ask Worker to process the data. "
            "After Worker responds, use send_message again to ask Worker to validate the result. "
            "Finally, respond with 'DONE'."
        ),
        model_settings=ModelSettings(temperature=0.0),
        tools=[get_market_data],
    )

    worker = Agent(
        name="Worker",
        description="Data processor",
        instructions=(
            "When asked to process: use process_data tool and respond 'Processed'. "
            "When asked to validate: use validate_result tool and respond 'Validated'."
        ),
        model_settings=ModelSettings(temperature=0.0),
        tools=[process_data, validate_result],
    )

    agency = Agency(
        coordinator,
        communication_flows=[coordinator > worker],
        shared_instructions="",
    )

    before = len(agency.thread_manager.get_all_messages())

    # Collect stream events
    stream_items: list[tuple[str, str, str | None]] = []
    async for event in agency.get_response_stream(message="Execute multiple tasks."):
        if hasattr(event, "item") and event.item is not None:
            item = event.item
            evt_type = getattr(item, "type", None)
            agent_name = getattr(event, "agent", None)
            tool_name = None
            if evt_type == "tool_call_item":
                raw = getattr(item, "raw_item", None)
                tool_name = getattr(raw, "name", None)
            if isinstance(evt_type, str) and isinstance(agent_name, str):
                stream_items.append((evt_type, agent_name, tool_name))

    # Verify stream matches expected
    assert stream_items == EXPECTED_FLOW_MULTIPLE_CALLS, (
        f"Multiple calls stream mismatch:\n got={stream_items}\n exp={EXPECTED_FLOW_MULTIPLE_CALLS}"
    )

    # Verify saved messages
    all_messages = agency.thread_manager.get_all_messages()
    new_messages = all_messages[before:]

    comparable: list[dict[str, Any]] = []
    for m in new_messages:
        t = m.get("type")
        role = m.get("role")
        if t in {"function_call", "function_call_output"} or role == "assistant":
            comparable.append(m)

    _assert_sanitized_history(comparable)


# Expected flow for nested delegation (A->B->C) based on actual execution
EXPECTED_FLOW_NESTED: list[tuple[str, str, str | None]] = [
    ("message_output_item", "AgentA", None),
    ("tool_call_item", "AgentA", "send_message"),  # A delegates to B
    ("tool_call_item", "AgentB", "send_message"),  # B delegates to C
    ("tool_call_item", "AgentB", "analyze_risk"),  # C's tool call attributed via B stream
    ("tool_call_output_item", "AgentB", None),
    ("message_output_item", "AgentB", None),
    ("tool_call_output_item", "AgentB", None),
    ("tool_call_item", "AgentB", "process_data"),  # B processes
    ("tool_call_output_item", "AgentB", None),
    ("message_output_item", "AgentB", None),
    ("tool_call_output_item", "AgentA", None),
    ("message_output_item", "AgentA", None),  # Final response
]


@pytest.mark.asyncio
async def test_nested_delegation_streaming() -> None:
    """Proves nested A→B→C delegation appears in stream and AgentA completes after sub-chain."""
    agent_a = Agent(
        name="AgentA",
        description="Top-level coordinator",
        instructions=(
            "First say 'ACK'. "
            "Then use send_message to ask AgentB to process and analyze data. "
            "Finally respond with 'Complete'."
        ),
        model_settings=ModelSettings(temperature=0.0),
        tools=[],
    )

    agent_b = Agent(
        name="AgentB",
        description="Middle processor",
        instructions=(
            "When asked by AgentA: "
            "First use send_message to ask AgentC to analyze risk. "
            "Then use process_data tool with the response. "
            "Finally respond 'Processed'."
        ),
        model_settings=ModelSettings(temperature=0.0),
        tools=[process_data],
    )

    agent_c = Agent(
        name="AgentC",
        description="Risk analyzer",
        instructions="When asked: use analyze_risk tool and respond 'Risk analyzed'.",
        model_settings=ModelSettings(temperature=0.0),
        tools=[analyze_risk],
    )

    agency = Agency(
        agent_a,
        communication_flows=[agent_a > agent_b, agent_b > agent_c],
        shared_instructions="",
    )

    before = len(agency.thread_manager.get_all_messages())

    # Collect stream events
    stream_items: list[tuple[str, str, str | None]] = []
    async for event in agency.get_response_stream(message="Start nested delegation."):
        if hasattr(event, "item") and event.item is not None:
            item = event.item
            evt_type = getattr(item, "type", None)
            agent_name = getattr(event, "agent", None)
            tool_name = None
            if evt_type == "tool_call_item":
                raw = getattr(item, "raw_item", None)
                tool_name = getattr(raw, "name", None)
            if isinstance(evt_type, str) and isinstance(agent_name, str):
                stream_items.append((evt_type, agent_name, tool_name))

    # Verify stream contains the required sequence in order and AgentC performs analyze_risk
    required_seq = [
        ("tool_call_item", "AgentA", "send_message"),
        ("tool_call_item", "AgentB", "send_message"),
        ("tool_call_item", "AgentC", "analyze_risk"),
        ("tool_call_output_item", "AgentA", None),
        ("message_output_item", "AgentA", None),
    ]

    def is_subsequence(needles: list[tuple[str, str, str | None]], haystack: list[tuple[str, str, str | None]]) -> bool:
        i = 0
        for item in haystack:
            if i < len(needles) and item == needles[i]:
                i += 1
        return i == len(needles)

    assert is_subsequence(required_seq, stream_items), (
        f"Nested delegation stream mismatch (required subsequence not found):\n got={stream_items}\n req={required_seq}"
    )

    # Verify saved messages
    all_messages = agency.thread_manager.get_all_messages()
    new_messages = all_messages[before:]

    comparable: list[dict[str, Any]] = []
    for m in new_messages:
        t = m.get("type")
        role = m.get("role")
        if t in {"function_call", "function_call_output"} or role == "assistant":
            comparable.append(m)

    _assert_sanitized_history(comparable)

    # Verify stream contains the required sequence in order (for saved messages verification)
    required_seq = [
        ("tool_call_item", "AgentA", "send_message"),
        ("tool_call_item", "AgentB", "send_message"),
        ("tool_call_output_item", "AgentA", None),
        ("message_output_item", "AgentA", None),
    ]
    assert is_subsequence(required_seq, stream_items), (
        f"Nested delegation stream mismatch (required subsequence not found):\n got={stream_items}\n req={required_seq}"
    )


# Helper to confirm specific tool calls were persisted for an agent
def _assert_tool_call_recorded(
    messages: list[dict[str, Any]], agent_name: str, tool_name: str, *, context: str
) -> None:
    for message in messages:
        if message.get("type") != "function_call":
            continue
        if message.get("name") != tool_name:
            continue
        recorded_agent = message.get("agent") or message.get("callerAgent")
        if str(recorded_agent) == agent_name:
            return
    raise AssertionError(f"Expected {context}: agent '{agent_name}' did not record function_call '{tool_name}'")


# Expected flow for parallel sub-agent calls (to different agents)
EXPECTED_FLOW_PARALLEL: list[tuple[str, str, str | None]] = [
    ("tool_call_item", "Orchestrator", "get_market_data"),  # Get initial data arrives first via tool_called
    ("message_output_item", "Orchestrator", None),  # ACK
    ("tool_call_output_item", "Orchestrator", None),
    ("tool_call_item", "Orchestrator", "send_message"),
    ("tool_call_item", "ProcessorA", "process_data"),  # ProcessorA works
    ("tool_call_output_item", "ProcessorA", None),
    ("message_output_item", "ProcessorA", None),
    ("tool_call_output_item", "Orchestrator", None),
    ("tool_call_item", "Orchestrator", "send_message"),
    ("tool_call_item", "ProcessorB", "validate_result"),  # ProcessorB works
    ("tool_call_output_item", "ProcessorB", None),
    ("message_output_item", "ProcessorB", None),
    ("tool_call_output_item", "Orchestrator", None),
    ("tool_call_item", "Orchestrator", "combine_results"),
    ("tool_call_output_item", "Orchestrator", None),
    ("message_output_item", "Orchestrator", None),  # Final response
]


@pytest.mark.asyncio
async def test_parallel_subagent_calls() -> None:
    """Proves orchestrator issues two sub-agent calls and completion follows canonical order."""
    orchestrator = Agent(
        name="Orchestrator",
        description="Main orchestrator",
        instructions=(
            "First say 'ACK'. Then call get_market_data('DATA'). "
            "Then use send_message to ask ProcessorA to process the data. "
            "After ProcessorA responds, use send_message to ask ProcessorB to validate. "
            "Finally, use combine_results tool and respond 'All done'."
        ),
        model_settings=ModelSettings(temperature=0.0),
        tools=[get_market_data, combine_results],
    )

    processor_a = Agent(
        name="ProcessorA",
        description="Data processor",
        instructions="When asked: use process_data tool and respond 'ProcessorA complete'.",
        model_settings=ModelSettings(temperature=0.0),
        tools=[process_data],
    )

    processor_b = Agent(
        name="ProcessorB",
        description="Result validator",
        instructions="When asked: use validate_result tool and respond 'ProcessorB complete'.",
        model_settings=ModelSettings(temperature=0.0),
        tools=[validate_result],
    )

    agency = Agency(
        orchestrator,
        communication_flows=[orchestrator > processor_a, orchestrator > processor_b],
        shared_instructions="",
    )

    before = len(agency.thread_manager.get_all_messages())

    # Collect stream events
    stream_items: list[tuple[str, str, str | None]] = []
    async for event in agency.get_response_stream(message="Coordinate parallel work."):
        if hasattr(event, "item") and event.item is not None:
            item = event.item
            evt_type = getattr(item, "type", None)
            agent_name = getattr(event, "agent", None)
            tool_name = None
            if evt_type == "tool_call_item":
                raw = getattr(item, "raw_item", None)
                tool_name = getattr(raw, "name", None)
            if isinstance(evt_type, str) and isinstance(agent_name, str):
                stream_items.append((evt_type, agent_name, tool_name))

    # Verify stream matches expected
    if stream_items != EXPECTED_FLOW_PARALLEL:
        logger.error(
            "Parallel sub-agent stream mismatch",
            extra={
                "got": stream_items,
                "expected": EXPECTED_FLOW_PARALLEL,
            },
        )
    assert stream_items == EXPECTED_FLOW_PARALLEL, (
        f"Parallel calls stream mismatch:\n got={stream_items}\n exp={EXPECTED_FLOW_PARALLEL}"
    )

    # Verify saved messages
    all_messages = agency.thread_manager.get_all_messages()
    new_messages = all_messages[before:]

    comparable: list[dict[str, Any]] = []
    for m in new_messages:
        t = m.get("type")
        role = m.get("role")
        if t in {"function_call", "function_call_output"} or role == "assistant":
            comparable.append(m)

    _assert_tool_call_recorded(new_messages, "ProcessorA", "process_data", context="parallel workflow")
    _assert_tool_call_recorded(new_messages, "ProcessorB", "validate_result", context="parallel workflow")
    _assert_sanitized_history(comparable)

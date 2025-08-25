"""
Deterministic streaming order test with two agents and custom tools.
"""

from typing import Any

import pytest
from agents import ModelSettings, function_tool

from agency_swarm import Agency, Agent

# Hardcoded expected flow (normalized stream type, agent, tool_name)
# Note: SDK sends send_message AFTER sub-agent completes (natural order)
EXPECTED_FLOW: list[tuple[str, str, str | None]] = [
    ("message_output_item", "MainAgent", None),
    ("tool_call_item", "MainAgent", "get_market_data"),
    ("tool_call_output_item", "MainAgent", None),
    ("tool_call_item", "SubAgent", "analyze_risk"),  # Sub-agent events come first
    ("tool_call_output_item", "SubAgent", None),
    ("message_output_item", "SubAgent", None),
    ("tool_call_item", "MainAgent", "send_message"),  # SDK sends this after sub-agent
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
async def test_full_streaming_flow_hardcoded_sequence():
    main = Agent(
        name="MainAgent",
        description="Coordinator",
        instructions=(
            "First say 'ACK'. Then call get_market_data('AAPL'). "
            "Then use the send_message tool to ask SubAgent to analyze the data and reply. "
            "Finally, respond to the user with a brief conclusion."
        ),
        model_settings=ModelSettings(temperature=0.0),
        tools=[get_market_data],
    )

    helper = Agent(
        name="SubAgent",
        description="Risk analyzer",
        instructions=("When prompted by MainAgent: call analyze_risk on the provided data, then reply succinctly."),
        model_settings=ModelSettings(temperature=0.0),
        tools=[analyze_risk],
    )

    agency = Agency(
        main,
        communication_flows=[(main, helper)],
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

    # Stream must equal hardcoded expected sequence
    assert stream_items == EXPECTED_FLOW, f"Stream flow mismatch:\n got={stream_items}\n exp={EXPECTED_FLOW}"

    # Normalize saved messages to stream-equivalent triples inline
    saved_normalized: list[tuple[str, str, str | None]] = []
    for m in comparable:
        t = m.get("type")
        role = m.get("role")
        agent = m.get("agent")
        tool_name = None
        if t == "function_call":
            # Accept flat shape (preferred) and legacy nested
            tool_name = m.get("name")
            if not tool_name:
                fn = m.get("function_call") or {}
                tool_name = fn.get("name")
            norm = "tool_call_item"
        elif t == "function_call_output":
            norm = "tool_call_output_item"
        else:
            norm = "message_output_item" if role == "assistant" else (t or "unknown")
        saved_normalized.append((norm, agent, tool_name))

    # Saved messages: compare minimal invariant (type + agent) to reduce coupling
    saved_min = [(t, a) for (t, a, _n) in saved_normalized]
    expected_min = [(t, a) for (t, a, _n) in EXPECTED_FLOW]
    assert saved_min == expected_min, f"Saved minimal order mismatch:\n got={saved_min}\n exp={expected_min}"

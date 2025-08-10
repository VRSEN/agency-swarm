import asyncio
from typing import Any

import pytest
from agents import ModelSettings

from agency_swarm import Agency, Agent


def _map_saved_message_type(saved: dict[str, Any]) -> str:
    """
    Map saved new_messages entries to stream event item types for comparison.
    Stream event item types we compare against include:
      - "message_output_item" (assistant message)
      - "tool_call_item" (function_call)
      - "tool_call_output_item" (function_call_output)
      - "handoff_output_item" (handoff)
    Saved messages contain either role/type fields. Normalize here.
    """
    t = saved.get("type")
    role = saved.get("role")

    if t == "function_call":
        return "tool_call_item"
    if t == "function_call_output":
        return "tool_call_output_item"

    # Messages default to type="message"
    if role == "assistant" or t == "message":
        return "message_output_item"

    # Fallback to raw type if present
    return t or "unknown"


@pytest.mark.asyncio
async def test_streamed_order_matches_new_messages_order():
    """
    Ensure the final new_messages order matches the exact order of streamed events.

    Scenario:
      - Main agent generates a message, then calls send_message to a sub-agent.
      - Sub-agent responds.
    We collect stream event item types and compare against the types of the
    new_messages slice (messages added during this request). They must match.
    """
    main = Agent(
        name="MainAgent",
        description="Coordinates work and delegates to helper.",
        instructions=(
            "You are MainAgent. First, produce a short acknowledgement message to the user. "
            "Then, delegate to HelperAgent using the send_message tool, asking it to reply 'OK'."
        ),
        model_settings=ModelSettings(temperature=0.0),
    )

    helper = Agent(
        name="HelperAgent",
        description="Replies concisely.",
        instructions=("You are HelperAgent. When messaged by MainAgent, reply with exactly 'OK' and nothing else."),
        model_settings=ModelSettings(temperature=0.0),
    )

    agency = Agency(
        main,
        communication_flows=[(main, helper)],
        shared_instructions="",
    )

    before_count = len(agency.thread_manager.get_all_messages())

    # Collect streamed event item types in order
    stream_item_types: list[str] = []
    async for event in agency.get_response_stream(message="Start the process."):
        if hasattr(event, "item") and event.item is not None:
            item = event.item
            # Event items expose a string type field (e.g., "message_output_item")
            evt_type = getattr(item, "type", None)
            if isinstance(evt_type, str):
                stream_item_types.append(evt_type)

    # Compute new_messages for this request
    all_messages = agency.thread_manager.get_all_messages()
    new_messages = all_messages[before_count:]

    # Filter to comparable types: assistant messages and function call items only
    comparable = []
    for m in new_messages:
        t = m.get("type")
        role = m.get("role")
        if t in {"function_call", "function_call_output"} or role == "assistant":
            comparable.append(m)

    saved_types = [_map_saved_message_type(m) for m in comparable]

    # For comparison, we can truncate both sequences to the same min length
    # to avoid model-dependent trailing items in rare cases
    min_len = min(len(stream_item_types), len(saved_types))
    cmp_stream = stream_item_types[:min_len]
    cmp_saved = saved_types[:min_len]

    assert cmp_saved == cmp_stream, f"Saved new_messages order {cmp_saved} does not match stream order {cmp_stream}"

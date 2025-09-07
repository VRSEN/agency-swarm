"""
Agency Swarm Streaming Demo

Simple demonstration of real-time streaming in Agency Swarm v1.x.
Shows how to handle streaming events and filter text vs tool call data.
"""

import asyncio
import logging
import os
import sys

# Path setup for standalone examples
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agency_swarm import Agency, Agent, function_tool

# ===== DEBUG CONFIGURATION =====
# Set to True to see ALL raw events for frontend integration
# Set to "verbose" to see raw events
DEBUG_MODE = False

logging.basicConfig(level=logging.WARNING)


# --- Logging Configuration --- #
def print_event_info(event, event_count):
    # Extract key fields
    agent_name = getattr(event, "agent", None)
    caller_agent = getattr(event, "callerAgent", None)
    event_type = getattr(event, "type", None)
    call_id = getattr(event, "call_id", None)
    item_id = getattr(event, "item_id", None)

    # For data events, get the nested type
    if hasattr(event, "data") and hasattr(event.data, "type"):
        data_type = event.data.type
    else:
        data_type = None

    # Format the output
    print(f"\n[EVENT #{event_count}]")
    print(f"  agent: {agent_name}")
    print(f"  callerAgent: {caller_agent}")
    if call_id:
        print(f"  call_id: {call_id}")
    if item_id:
        print(f"  item_id: {item_id}")
    print(f"  event.type: {event_type}")
    if data_type:
        print(f"  data.type: {data_type}")

    # Show raw event only if verbose
    if DEBUG_MODE == "verbose":
        print(f"  Raw: {event}")


# --- Simple Tool --- #


@function_tool
def get_weather(location: str) -> str:
    """Get weather information for a location."""
    return f"The weather in {location} is sunny, 22°C with light winds."


# --- Agent Setup --- #


def create_demo_agency():
    """Create a demo agency for terminal demo"""

    ceo = Agent(
        name="CEO",
        description="Chief Executive Officer - oversees all operations",
        instructions="You are the CEO. When asked about weather, delegate to Worker with a specific location (use London if not specified).",
        tools=[],
    )

    worker = Agent(
        name="Worker",
        description="Worker - performs tasks and writes weather reports",
        instructions="You handle weather tasks. Use the get_weather tool which returns weather reports.",
        tools=[get_weather],
    )

    # Create agency with communication flows (v1.x pattern)
    agency = Agency(
        ceo,  # Entry point agent (positional argument)
        communication_flows=[ceo > worker],
        name="TerminalDemoAgency",
    )

    return agency


agency = create_demo_agency()

# --- Streaming Handler --- #


async def stream_response(message: str):
    """Stream a response and handle events properly."""
    print(f"\nStreaming: {message}")
    print("Response: ", end="", flush=True)

    full_text = ""
    event_count = 0

    async for event in agency.get_response_stream(message):
        event_count += 1

        # Debug logging for frontend developers
        if DEBUG_MODE:
            print_event_info(event, event_count)

        # Normal streaming logic
        if hasattr(event, "data"):
            data = event.data

            # Only capture actual response text, not tool call arguments
            if hasattr(data, "delta") and hasattr(data, "type"):
                if data.type == "response.output_text.delta":
                    # Stream the actual response text in real-time
                    delta_text = data.delta
                    if delta_text:
                        if not DEBUG_MODE:
                            print(delta_text, end="", flush=True)
                        full_text += delta_text
                # Skip tool call deltas (we don't want to show those to users)
                elif data.type == "response.function_call_arguments.delta":
                    continue

        # Handle validation errors
        elif isinstance(event, dict):
            event_type = event.get("event", event.get("type"))
            if event_type == "error":
                print(f"\n❌ Error: {event.get('content', event.get('data', 'Unknown error'))}")
                break

    if DEBUG_MODE:
        print(f"\nTotal events received: {event_count}")

    print("\n✅ Stream complete")
    print(f"Total: {len(full_text)} characters streamed")
    return full_text


# --- Main Demo --- #


async def main():
    """Run simple streaming demo."""
    print("Agency Swarm Streaming Demo")
    print("=" * 40)
    print("Watch text stream in real-time.")

    await stream_response("What's the weather in London?")

    print("\nDemo complete!")


if __name__ == "__main__":
    asyncio.run(main())

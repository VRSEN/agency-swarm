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

from agents import function_tool

from agency_swarm import Agency, Agent

# Minimal logging setup
logging.basicConfig(level=logging.WARNING)

# --- Simple Tool --- #


@function_tool
def get_weather(location: str) -> str:
    """Get weather information for a location."""
    return f"The weather in {location} is sunny, 22°C with light winds."


# --- Agent Setup --- #

agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant. Use tools when appropriate and provide clear responses.",
    tools=[get_weather],
)

agency = Agency(agent)

# --- Streaming Handler --- #


async def stream_response(message: str):
    """Stream a response and handle events properly."""
    print(f"\n🔥 Streaming: {message}")
    print("📡 Response: ", end="", flush=True)

    full_text = ""

    async for event in agency.get_response_stream(message):
        # Handle streaming events with data
        if hasattr(event, "data"):
            data = event.data

            # Only capture actual response text, not tool call arguments
            if hasattr(data, "delta") and hasattr(data, "type"):
                if data.type == "response.output_text.delta":
                    # Stream the actual response text in real-time
                    delta_text = data.delta
                    if delta_text:
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

    print("\n✅ Stream complete")
    print(f"📋 Total: {len(full_text)} characters streamed")
    return full_text


# --- Main Demo --- #


async def main():
    """Run simple streaming demo."""
    print("🌟 Agency Swarm Streaming Demo")
    print("=" * 40)
    print("🎯 Watch text stream in real-time!")

    # Test basic streaming
    await stream_response("Hello! Tell me about yourself.")

    # Test with tool call
    await stream_response("What's the weather in London?")

    # Test longer response
    await stream_response("Write a short poem about artificial intelligence.")

    print("\n🎉 Demo complete! Streaming works perfectly.")


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Set OPENAI_API_KEY environment variable")
        sys.exit(1)

    asyncio.run(main())

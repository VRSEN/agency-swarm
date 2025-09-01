"""
FastAPI Server Example for Agency Swarm v1.x

This example demonstrates how to serve agencies via FastAPI with proper
streaming support, showing agent and callerAgent fields in responses.

To run:
1. Set your OPENAI_API_KEY environment variable
2. Run: python server.py
3. Test with the client.py script or via curl/Postman
"""

import os
import sys

# Path setup for standalone examples
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from agents import function_tool

from agency_swarm import Agency, Agent, run_fastapi

# --- Simple Tools --- #


@function_tool
def ExampleTool(name: str, greeting_type: str = "Hello") -> str:
    """A tool that provides a simple greeting message with customization options.
    This tool can be used to generate personalized greetings for users."""
    return f"{greeting_type}, {name}!"


# --- Agent Setup --- #


def create_agency(load_threads_callback=None):
    """Create a demo agency with two agents for testing communication flows."""

    # First agent - receives user requests
    agent = Agent(
        name="ExampleAgent",
        description="Primary agent that handles user requests",
        instructions="""You are the primary agent. When asked to call the second agent:
        1. Use the send_message tool to communicate with ExampleAgent2
        2. Have ExampleAgent2 use the ExampleTool
        3. Return the result to the user""",
        tools=[],
    )

    # Second agent - performs tasks
    agent2 = Agent(
        name="ExampleAgent2",
        description=(
            "A helpful and knowledgeable assistant that provides "
            "comprehensive support and guidance across various domains."
        ),
        instructions="You are a helpful assistant. Use the ExampleTool when asked to greet someone.",
        tools=[ExampleTool],
    )

    # Create agency with communication flow
    agency = Agency(
        agent,
        agent2,
        communication_flows=[agent > agent2],
        shared_instructions="Be helpful and demonstrate inter-agent communication.",
        load_threads_callback=load_threads_callback,
    )

    return agency


# --- Main --- #

if __name__ == "__main__":
    print("🚀 Starting FastAPI server for Agency Swarm")
    print("=" * 50)
    print("📍 Server will run at: http://localhost:8080")
    print("📝 Available endpoints:")
    print("  - POST /my-agency/get_response")
    print("  - POST /my-agency/get_response_stream (SSE)")
    print("  - GET /my-agency/get_metadata")
    print("=" * 50)

    # Run the FastAPI server
    run_fastapi(
        agencies={
            "my-agency": create_agency,
        },
        port=8080,
        app_token_env="APP_TOKEN",  # Optional: Set APP_TOKEN env var for authentication
    )

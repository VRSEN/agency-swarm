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
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Literal

# Path setup for standalone examples
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from agency_swarm import (
    Agency,
    Agent,
    Handoff,
    ModelSettings,
    Reasoning,
    WebSearchTool,
    function_tool,
    run_fastapi,
)

# --- Simple Tools --- #


@function_tool
def CalculationTool(
    a: float,
    b: float,
    operation: Literal["add", "subtract", "multiply", "divide"] = "add",
) -> str:
    """Perform a basic arithmetic operation on two numbers."""
    if operation == "add":
        result = a + b
    elif operation == "subtract":
        result = a - b
    elif operation == "multiply":
        result = a * b
    elif operation == "divide":
        if b == 0:
            return "Error: Cannot divide by zero."
        result = a / b
    return f"Result: {result}"


# --- Agent Setup --- #


def create_agency(load_threads_callback=None):
    """Create a demo agency with two agents for testing communication flows."""

    # First agent - receives user requests
    agent = Agent(
        name="UserSupportAgent",
        description="Receives and coordinates user requests.",
        instructions=(
            "You are UserSupportAgent. Route and handle user requests as needed. "
            "Use your file tools when the user asks about files or asks to analyze data."
        ),
        files_folder=_prepare_runtime_files_folder(),
        include_search_results=True,
        tools=[WebSearchTool()],
        model="gpt-5.4-mini",
        model_settings=ModelSettings(reasoning=Reasoning(effort="low", summary="auto")),
    )

    # Second agent - performs tasks
    agent2 = Agent(
        name="MathAgent",
        description="Handles all math queries using CalculationTool.",
        instructions="You are MathAgent. Use CalculationTool for arithmetic questions.",
        tools=[CalculationTool],
        model="gpt-5.4-mini",
        model_settings=ModelSettings(reasoning=Reasoning(effort="high", summary="auto")),
    )

    # Create agency with communication flow
    agency = Agency(
        agent,
        agent2,
        communication_flows=[(agent, agent2, Handoff)],
        shared_instructions="Demonstrate inter-agent communication.",
        load_threads_callback=load_threads_callback,
    )

    return agency


def _prepare_runtime_files_folder() -> str:
    """Create a disposable copy of examples/data for file-tool testing."""
    source_folder = Path(__file__).resolve().parent.parent / "data"
    if not source_folder.exists():
        raise FileNotFoundError(f"Expected example data directory at: {source_folder}")

    runtime_root = Path(tempfile.mkdtemp(prefix="agency-swarm-fastapi-files-"))
    files_folder = runtime_root / "files"
    shutil.copytree(source_folder, files_folder)
    return str(files_folder)


# --- Main --- #

if __name__ == "__main__":
    print("Starting FastAPI server for Agency Swarm")
    print("=" * 50)
    print("📍 Server will run at: http://localhost:8080")
    print("Available endpoints:")
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

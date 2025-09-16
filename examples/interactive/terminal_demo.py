"""
Agency Swarm Terminal Demo

This example demonstrates the Terminal UI capabilities of Agency Swarm v1.x.
To better demonstrate the features of the demo, ask the CEO agent to get weather in London.
You should see agent-to-agent communication, reasoning, and tool outputs in the terminal.
"""

import sys
from pathlib import Path

from agents import ModelSettings
from openai.types.shared import Reasoning

# Add the src directory to the path so we can import agency_swarm
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agency_swarm import Agency, Agent, function_tool


@function_tool
def get_weather(location: str) -> str:
    """Get weather information for a location."""
    return f"The weather in {location} is sunny, 22°C with light winds."


def create_demo_agency():
    """Create a demo agency for terminal demo."""

    # Create agents using v1.x pattern (direct instantiation)
    ceo = Agent(
        name="CEO",
        description="Chief Executive Officer - oversees all operations",
        instructions="You are the CEO.",
        model="gpt-5-mini",
        model_settings=ModelSettings(reasoning=Reasoning(effort="low", summary="auto")),
    )

    worker = Agent(
        name="Worker",
        description="Worker - performs weather-related tasks",
        instructions="You are a worker. You handle weather tasks. Use the get_weather tool with the location provided.",
        tools=[get_weather],
        model="gpt-5-mini",
        model_settings=ModelSettings(reasoning=Reasoning(effort="low", summary="auto")),
    )

    # Create a simple agency with one-directional communication flow
    agency = Agency(
        ceo,  # Entry point agent (positional argument)
        communication_flows=[
            (ceo > worker),
        ],
        name="TerminalDemoAgency",
    )

    return agency


agency = create_demo_agency()


if __name__ == "__main__":
    agency.terminal_demo(show_reasoning=True)

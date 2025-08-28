"""
Agency Swarm Terminal Demo

This example demonstrates the Terminal UI capabilities of Agency Swarm v1.x.
Sets up a frontend and backend server for the Terminal UI chat demo.
"""

import sys
from pathlib import Path

# Add the src directory to the path so we can import agency_swarm
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agents import function_tool

from agency_swarm import Agency, Agent


@function_tool
def get_weather(location: str) -> str:
    """Get weather information for a location."""
    return f"The weather in {location} is sunny, 22°C with light winds."


def create_demo_agency():
    """Create a demo agency for terminal demo"""

    # Create agents using v1.x pattern (direct instantiation)
    ceo = Agent(
        name="CEO",
        description="Chief Executive Officer - oversees all operations",
        instructions="You are the CEO. When asked about weather, delegate to Worker with a specific location (use London if not specified).",
    )

    worker = Agent(
        name="Worker",
        description="Worker - performs weather-related tasks",
        instructions="You are a worker. You handle weather tasks. Use the get_weather tool with the location provided.",
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


if __name__ == "__main__":
    agency.terminal_demo()

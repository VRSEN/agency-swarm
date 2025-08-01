"""
Agency Swarm Terminal Demo

This example demonstrates the Terminal UI capabilities of Agency Swarm v1.x.
Sets up a frontend and backend server for the Terminal UI chat demo.
"""

import sys
from pathlib import Path

# Add the src directory to the path so we can import agency_swarm
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agents import RunContextWrapper, function_tool
from dotenv import load_dotenv

from agency_swarm import Agency, Agent

load_dotenv()


@function_tool()
async def example_tool(wrapper: RunContextWrapper) -> str:
    """Example tool for terminal demo"""
    return "Example tool executed"


def create_demo_agency():
    """Create a demo agency for terminal demo"""

    # Create agents using v1.x pattern (direct instantiation)
    ceo = Agent(
        name="CEO",
        description="Chief Executive Officer - oversees all operations",
        instructions="You are the CEO responsible for high-level decision making and coordination.",
        tools=[example_tool],
    )

    worker = Agent(
        name="Worker",
        description="Worker - performs tasks",
        instructions="Follow instructions given by the CEO.",
        tools=[example_tool],
    )

    # Create agency with communication flows (v1.x pattern)
    agency = Agency(
        ceo,  # Entry point agent (positional argument)
        communication_flows=[
            (ceo, worker),
        ],
        name="TerminalDemoAgency",
    )

    return agency


agency = create_demo_agency()


if __name__ == "__main__":
    agency.terminal_demo()

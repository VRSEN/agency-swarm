"""
Agency Swarm ChatKit Demo

This example demonstrates the ChatKit UI capabilities of Agency Swarm v1.x.
Sets up a frontend and backend server for the OpenAI ChatKit UI chat demo.
"""

import sys
from pathlib import Path

# Add the src directory to the path so we can import agency_swarm
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agency_swarm import Agency, Agent, RunContextWrapper, function_tool


@function_tool()
async def example_tool(wrapper: RunContextWrapper) -> str:
    """Example tool for chatkit demo"""
    return "Example tool executed"


def create_demo_agency():
    """Create a demo agency for chatkit demo"""

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
        communication_flows=[ceo > worker],
        name="ChatKitDemoAgency",
    )

    return agency


def main():
    """Launch interactive ChatKit demo"""
    print("Agency Swarm ChatKit Demo")
    print("=" * 50)
    print()

    try:
        agency = create_demo_agency()
        # Launch the ChatKit UI demo with backend and frontend servers.
        agency.chatkit_demo()

    except Exception as e:
        print(f"❌ Demo failed with error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()

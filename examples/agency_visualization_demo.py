#!/usr/bin/env python3
"""
Agency Swarm Visualization Demo

This example demonstrates the interactive HTML visualization capabilities of Agency Swarm v1.x.
Creates a beautiful, interactive HTML file showing your agency structure with drag & drop,
zoom, and professional styling.
"""

import os
import sys
from pathlib import Path

# Add the src directory to the path so we can import agency_swarm
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agents import RunContextWrapper, function_tool

from agency_swarm import Agency, Agent


@function_tool()
async def example_tool(wrapper: RunContextWrapper) -> str:
    """Example tool for visualization demo"""
    return "Example tool executed"


def create_demo_agency():
    """Create a demo agency for visualization"""

    # Create agents using v1.x pattern (direct instantiation)
    ceo = Agent(
        name="CEO",
        description="Chief Executive Officer - oversees all operations",
        instructions="You are the CEO responsible for high-level decision making and coordination.",
        tools=[],
    )

    pm = Agent(
        name="ProjectManager",
        description="Manages project timelines and coordinates between teams",
        instructions="You manage projects, timelines, and coordinate between different teams.",
        tools=[example_tool],
    )

    dev = Agent(
        name="Developer",
        description="Writes and maintains code",
        instructions="You write, test, and maintain code for various projects.",
        tools=[example_tool],
    )

    qa = Agent(
        name="QA",
        description="Tests software and ensures quality",
        instructions="You test software, find bugs, and ensure quality standards.",
        tools=[example_tool],
    )

    # Create agency with communication flows (v1.x pattern)
    agency = Agency(
        ceo,  # Entry point agent (positional argument)
        communication_flows=[
            (ceo, pm),  # CEO can communicate with PM
            (pm, dev),  # PM can communicate with Developer
            (pm, qa),  # PM can communicate with QA
            (dev, qa),  # Developer can communicate with QA
        ],
        name="Software Development Agency",
        shared_instructions="This is a software development agency with clear hierarchy and communication flows.",
    )

    return agency


def main():
    """Generate interactive HTML visualization demo"""
    print("🚀 Agency Swarm Interactive Visualization Demo")
    print("=" * 50)
    print()

    # Create output directory
    os.makedirs("visualization_output", exist_ok=True)
    os.chdir("visualization_output")

    try:
        print("=== Interactive HTML Visualization ===\n")

        agency = create_demo_agency()

        # Generate interactive HTML visualization
        html_file = agency.visualize(
            output_file="agency_interactive_demo.html",
            layout_algorithm="hierarchical",
            include_tools=True,
            open_browser=True,  # auto-open the demo
        )

        file_size = os.path.getsize(html_file)
        print(f"  ✅ Generated: {html_file} ({file_size:,} bytes)")
        print("  📱 Features: Interactive drag & drop, zoom, professional styling")
        print("  📊 Includes: Agency statistics, communication flows, tool information")
        print()

        print("🎉 Demo completed successfully!")
        print(f"📁 Output file saved in: {os.getcwd()}")
        print("🌐 The HTML file should have opened in your browser automatically.")

    except Exception as e:
        print(f"❌ Demo failed with error: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # Return to original directory
        os.chdir("..")


if __name__ == "__main__":
    main()

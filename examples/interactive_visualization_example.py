#!/usr/bin/env python3
"""
Agency Swarm - Interactive Visualization Example

This demonstrates the modular visualization system.
"""

import sys
from pathlib import Path

# Add the src directory to the path so we can import agency_swarm
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agency_swarm import Agency, Agent, BaseTool


class ExampleTool(BaseTool):
    """Example tool for demonstration"""

    def __init__(self):
        super().__init__(name="ExampleTool", description="An example tool for visualization demo")

    def run(self, **kwargs):
        return "Example tool executed"


def create_demo_agency():
    """Create a demo software development agency"""

    # Create agents with different roles
    ceo = Agent(
        name="CEO",
        description="Chief Executive Officer - strategic oversight",
        instructions="You oversee all operations and make strategic decisions.",
        tools=[],
    )

    pm = Agent(
        name="ProjectManager",
        description="Manages timelines and coordinates teams",
        instructions="You manage projects and coordinate between teams.",
        tools=[ExampleTool()],
    )

    dev = Agent(
        name="Developer",
        description="Writes and maintains code",
        instructions="You write, test, and maintain code.",
        tools=[ExampleTool()],
    )

    qa = Agent(
        name="QA",
        description="Tests software and ensures quality",
        instructions="You test software and ensure quality standards.",
        tools=[ExampleTool()],
    )

    # Create agency with communication flows
    agency = Agency(
        ceo,  # Entry point agent
        communication_flows=[
            (ceo, pm),  # CEO → Project Manager
            (pm, dev),  # PM → Developer
            (pm, qa),  # PM → QA
            (dev, qa),  # Developer → QA
        ],
        name="Software Development Agency",
        shared_instructions="Software development with quality focus.",
    )

    return agency


def main():
    """Demonstrate the modular visualization system"""
    print("🚀 Agency Swarm - Interactive Visualization Demo")
    print("=" * 50)

    # Create demo agency
    agency = create_demo_agency()

    # Create visualization with hierarchical layout
    print("\nGenerating hierarchical layout visualization...")

    try:
        html_file = agency.create_interactive_visualization(
            output_file="agency_visualization.html",
            layout_algorithm="hierarchical",
            include_tools=True,
            open_browser=True,
        )

        print(f"  ✅ Generated: {html_file}")

    except Exception as e:
        print(f"  ❌ Error: {e}")

    print("\n🎉 Visualization generated!")
    print("\nFeatures included:")
    print("  ✨ Interactive drag and drop nodes")
    print("  🔍 Zoom and pan controls")
    print("  🎯 Hierarchical layout")
    print("  🛠️ Tool visibility toggle")
    print("  📊 Real-time statistics")
    print("  📱 Responsive design")
    print("  🔥 Styling")
    print("  ⚡ Simplified interface - only essential controls")

    print(f"\n📁 Files saved in: {Path.cwd()}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Agency Swarm Visualization Demo

This example demonstrates the visualization capabilities of Agency Swarm v1.x,
including both static chart generation and ReactFlow-compatible JSON output.
"""

import json
import os
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


class CEOAgent(Agent):
    """CEO Agent - the entry point of the agency"""

    def __init__(self):
        super().__init__(
            name="CEO",
            description="Chief Executive Officer - oversees all operations",
            instructions="You are the CEO responsible for high-level decision making and coordination.",
            tools=[],
        )


class ProjectManagerAgent(Agent):
    """Project Manager Agent"""

    def __init__(self):
        super().__init__(
            name="ProjectManager",
            description="Manages project timelines and coordinates between teams",
            instructions="You manage projects, timelines, and coordinate between different teams.",
            tools=[ExampleTool()],
        )


class DeveloperAgent(Agent):
    """Developer Agent"""

    def __init__(self):
        super().__init__(
            name="Developer",
            description="Writes and maintains code",
            instructions="You write, test, and maintain code for various projects.",
            tools=[ExampleTool()],
        )


class QAAgent(Agent):
    """Quality Assurance Agent"""

    def __init__(self):
        super().__init__(
            name="QA",
            description="Tests software and ensures quality",
            instructions="You test software, find bugs, and ensure quality standards.",
            tools=[ExampleTool()],
        )


def create_demo_agency():
    """Create a demo agency for visualization"""

    # Create agents
    ceo = CEOAgent()
    pm = ProjectManagerAgent()
    dev = DeveloperAgent()
    qa = QAAgent()

    # Create agency with communication flows (v1.x pattern)
    agency = Agency(
        ceo,  # Entry point agent (positional argument)
        communication_flows=[
            (ceo, pm),  # CEO can communicate with PM
            (pm, dev),  # PM can communicate with Developer
            (pm, qa),  # PM can communicate with QA
            (dev, qa),  # Developer can communicate with QA
        ],
        shared_instructions="This is a software development agency with clear hierarchy and communication flows.",
    )

    return agency


def demo_static_visualization():
    """Demonstrate static chart generation"""
    print("=== Static Chart Visualization Demo ===\n")

    agency = create_demo_agency()

    # Generate different layout types
    layouts = ["hierarchical", "force_directed"]

    for layout in layouts:
        print(f"Generating {layout} layout chart...")

        try:
            # Generate chart (with show_plot=False to avoid hanging in headless environments)
            agency.plot_agency_chart(
                layout=layout,
                show_plot=False,  # Don't display - just save
                save_path=f"agency_chart_{layout}.png",
                show_tools=True,
            )
            print(f"  ✅ Saved: agency_chart_{layout}.png")

        except Exception as e:
            print(f"  ❌ Error generating {layout} chart: {e}")

    print()


def demo_reactflow_json():
    """Demonstrate ReactFlow JSON generation"""
    print("=== ReactFlow JSON Generation Demo ===\n")

    agency = create_demo_agency()

    # Generate ReactFlow-compatible JSON for different layouts
    layouts = ["hierarchical", "force_directed"]

    for layout in layouts:
        print(f"Generating {layout} ReactFlow JSON...")

        try:
            # Get ReactFlow structure (all logic in agency.py)
            reactflow_data = agency.get_agency_structure(layout_algorithm=layout, include_tools=True)

            # Save to file
            output_file = f"agency_structure_{layout}.json"
            with open(output_file, "w") as f:
                json.dump(reactflow_data, f, indent=2)

            print(f"  ✅ Saved: {output_file}")

            # Show summary stats from metadata
            metadata = reactflow_data.get("metadata", {})
            print(f"    - Agents: {metadata.get('totalAgents', 0)}")
            print(f"    - Tools: {metadata.get('totalTools', 0)}")
            print(f"    - Communication flows: {len(reactflow_data.get('edges', []))}")
            print()

        except Exception as e:
            print(f"  ❌ Error generating {layout} JSON: {e}")


def demo_analysis():
    """Demonstrate analysis of agency structure"""
    print("=== Agency Structure Analysis ===\n")

    agency = create_demo_agency()

    try:
        # Get structure data (all logic in agency.py)
        structure = agency.get_agency_structure(include_tools=True)

        # Use metadata for summary (minimal processing)
        metadata = structure.get("metadata", {})
        edges = structure.get("edges", [])

        print("Agency Composition:")
        print(f"  - Total Agents: {metadata.get('totalAgents', 0)}")
        print(f"  - Total Tools: {metadata.get('totalTools', 0)}")
        print(f"  - Communication Flows: {len(edges)}")
        print(f"  - Entry Points: {', '.join(metadata.get('entryPoints', []))}")
        print()

        print("Communication Flows:")
        for edge in edges:
            if edge.get("type") == "communication":
                print(f"  - {edge['source']} → {edge['target']}")
        print()

        print("Agency Metadata:")
        for key, value in metadata.items():
            if key not in ["totalAgents", "totalTools", "entryPoints"]:  # Skip already shown
                print(f"  - {key}: {value}")
        print()

    except Exception as e:
        print(f"❌ Error analyzing structure: {e}")


def main():
    """Run all visualization demos"""
    print("🚀 Agency Swarm Visualization Demo")
    print("=" * 50)
    print()

    # Create output directory
    os.makedirs("visualization_output", exist_ok=True)
    os.chdir("visualization_output")

    try:
        # Run demos
        demo_static_visualization()
        demo_reactflow_json()
        demo_analysis()

        print("🎉 All demos completed successfully!")
        print(f"📁 Output files saved in: {os.getcwd()}")
        print()
        print("Generated files:")
        for file in os.listdir("."):
            if file.endswith((".png", ".json")):
                size = os.path.getsize(file)
                print(f"  - {file} ({size:,} bytes)")

    except Exception as e:
        print(f"❌ Demo failed with error: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # Return to original directory
        os.chdir("..")


if __name__ == "__main__":
    main()

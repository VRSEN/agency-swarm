#!/usr/bin/env python3
import sys

sys.path.insert(0, "../src")
from agency_swarm import Agency, Agent, BaseTool


class TestTool(BaseTool):
    def __init__(self):
        super().__init__(name="TestTool", description="A test tool")

    def run(self):
        return "test"


# Create agents with tools
ceo = Agent(name="CEO", description="Chief Executive", instructions="Lead the company", tools=[])
cto = Agent(name="CTO", description="Chief Technology Officer", instructions="Manage technology", tools=[TestTool()])
dev = Agent(name="Developer", description="Software Developer", instructions="Write code", tools=[TestTool()])

# Create agency with complex flows
agency = Agency(
    ceo, communication_flows=[(ceo, cto), (cto, dev), (ceo, dev)], shared_instructions="Complex test agency"
)

# Test both methods
print("=== Testing Complex Agency ===")
structure = agency.get_agency_structure(include_tools=True, layout_algorithm="circular")
print(f"Structure: {len(structure['nodes'])} nodes, {len(structure['edges'])} edges")

agency.plot_agency_chart(layout="hierarchical", save_path="complex_test.png", show_plot=False)
print("Chart saved successfully!")

# Test without tools
structure_no_tools = agency.get_agency_structure(include_tools=False)
print(f"No tools: {len(structure_no_tools['nodes'])} nodes, {len(structure_no_tools['edges'])} edges")
print("All tests passed!")

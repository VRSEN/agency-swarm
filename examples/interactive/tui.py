"""
Agency Swarm TUI example.

This example is the main product-style demo for `agency.tui()`.
It intentionally exercises these core surfaces:

- reasoning
- handoffs
- web search
- arithmetic

Suggested prompts:
- "Search the web for the latest Bun release notes."
- "What is 345 * 18?"
- "Explain when to use a handoff between agents."
"""

import sys
from pathlib import Path
from typing import Literal

# Add the src directory to the path so we can import agency_swarm
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agency_swarm import Agency, Agent, Handoff, ModelSettings, Reasoning, WebSearchTool, function_tool


@function_tool
def calculate(a: float, b: float, operation: Literal["add", "subtract", "multiply", "divide"] = "add") -> str:
    """Perform a basic arithmetic operation."""
    if operation == "add":
        value = a + b
    elif operation == "subtract":
        value = a - b
    elif operation == "multiply":
        value = a * b
    else:
        if b == 0:
            return "Error: Cannot divide by zero."
        value = a / b
    return f"Result: {value}"


def create_demo_agency() -> Agency:
    """Create a richer TUI demo agency for manual QA."""
    support = Agent(
        name="UserSupportAgent",
        description="Receives user requests and coordinates reasoning, search, and handoffs.",
        instructions=(
            "You are UserSupportAgent. Handle general requests, reason step by step when useful, "
            "use web search when the user asks for current information, and hand off math-heavy "
            "work to MathAgent."
        ),
        include_search_results=True,
        tools=[WebSearchTool()],
        model="gpt-5.4-mini",
        model_settings=ModelSettings(reasoning=Reasoning(effort="low", summary="auto")),
        conversation_starters=[
            "Search the web for the latest Bun release notes.",
            "What is 345 * 18?",
            "Explain when to use a handoff between agents.",
        ],
    )

    math = Agent(
        name="MathAgent",
        description="Handles arithmetic and calculation-heavy requests.",
        instructions="You are MathAgent. Use the calculate tool for arithmetic questions.",
        tools=[calculate],
        model="gpt-5.4-mini",
        model_settings=ModelSettings(reasoning=Reasoning(effort="high", summary="auto")),
    )

    return Agency(
        support,
        math,
        communication_flows=[(support, math, Handoff)],
        shared_instructions="Demonstrate reasoning, web search, arithmetic, and handoffs.",
        name="TuiDemoAgency",
    )


if __name__ == "__main__":
    create_demo_agency().tui(show_reasoning=True)

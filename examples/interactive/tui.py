"""
Agency Swarm TUI example.

This example is the main product-style demo for `agency.tui()`.
It intentionally exercises the same important surfaces as the richer FastAPI
example:

- reasoning
- handoffs
- web search
- file search
- code/file analysis through the files folder

Suggested prompts:
- "Tell me about daily_revenue_report.pdf."
- "Search the web for the latest Bun release notes."
- "What is 345 * 18?"
- "Compare the findings in research_report.txt with daily_revenue_report.pdf."
"""

import atexit
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Literal

# Add the src directory to the path so we can import agency_swarm
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agency_swarm import Agency, Agent, Handoff, ModelSettings, Reasoning, WebSearchTool, function_tool


def _files() -> str:
    source = Path(__file__).resolve().parent.parent / "data"
    if not source.exists():
        raise FileNotFoundError(f"Expected example data directory at: {source}")

    root = Path(tempfile.mkdtemp(prefix="agency-swarm-terminal-demo-"))
    path = root / "files"
    shutil.copytree(source, path)
    atexit.register(lambda: shutil.rmtree(root, ignore_errors=True))
    return str(path)


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
        description="Receives user requests and coordinates reasoning, search, and file work.",
        instructions=(
            "You are UserSupportAgent. Handle general requests, reason step by step when useful, "
            "use your web and file tools when the user asks about files or the web, and hand off "
            "math-heavy work to MathAgent. When files contain charts, reports, or data, use the "
            "available file/code tools to inspect them before answering."
        ),
        # files_folder=_files(),
        include_search_results=True,
        tools=[WebSearchTool()],
        model="gpt-5.4-mini",
        model_settings=ModelSettings(reasoning=Reasoning(effort="low", summary="auto")),
        conversation_starters=[
            "Tell me about daily_revenue_report.pdf.",
            "Search the web for the latest Bun release notes.",
            "What is 345 * 18?",
            "Compare research_report.txt with daily_revenue_report.pdf.",
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
        shared_instructions="Demonstrate reasoning, web search, file search, and handoffs.",
        name="TuiDemoAgency",
    )


if __name__ == "__main__":
    create_demo_agency().tui(show_reasoning=True)

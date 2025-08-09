"""
Observability demo showing OpenAI (built-in), Langfuse and AgentOps tracing.

Run with: python examples/observability_demo.py
"""

import asyncio
import logging
import os
import sys
from statistics import mean, stdev
from typing import Any

from dotenv import load_dotenv

# Path setup for standalone examples
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

import agentops  # noqa: E402
from agents import ModelSettings, RunContextWrapper, function_tool, trace  # noqa: E402
from langfuse import observe  # noqa: E402

from agency_swarm import Agency, Agent  # noqa: E402

load_dotenv(override=True)
logging.basicConfig(level=logging.INFO)


# ────────────────────────────────
# Tool definition
# ────────────────────────────────


@function_tool
async def analyze_dataset(ctx: RunContextWrapper[Any], dataset: list[int]) -> str:
    """Analyze a dataset and return basic statistics."""
    print(f"DATASET ANALYZED by {ctx.context.current_agent_name}: {dataset}")
    return f"Mean: {mean(dataset):.1f}, Standard Deviation: {stdev(dataset):.1f}"


# ────────────────────────────────
# Agency definition (agents + flows)
# ────────────────────────────────


def create_agency() -> Agency:
    """Create agency with CEO, Developer, and Analyst."""
    ceo = Agent(
        name="CEO",
        instructions="You are the CEO. NEVER execute tasks yourself. Instead, DELEGATE all tasks: coding tasks to Developer and data analysis to DataAnalyst.",
        description="Manages projects and coordinates between team members",
        model="gpt-4.1",
        model_settings=ModelSettings(temperature=0.0),
    )

    developer = Agent(
        name="Developer",
        instructions="You are the Developer. Solve coding problems by implementing solutions and writing code.",
        description="Implements technical solutions and writes code",
        model="gpt-4.1",
        model_settings=ModelSettings(temperature=0.0),
    )

    analyst = Agent(
        name="DataAnalyst",
        instructions="You are the Data Analyst. Analyze data and provide insights. Always use analyze_dataset in your response to process the dataset.",
        description="Analyzes data and provides insights",
        model="gpt-4.1",
        tools=[analyze_dataset],
        model_settings=ModelSettings(temperature=0.0),
    )

    return Agency(
        ceo,
        communication_flows=[
            (ceo, developer),
            (ceo, analyst),
        ],
    )


# ────────────────────────────────
# Example tracing wrappers
# ────────────────────────────────
async def openai_tracing(input_message: str) -> str:
    agency_instance = create_agency()
    with trace("OpenAI tracing"):
        response = await agency_instance.get_response(message=input_message)
    return response.final_output


@observe()
async def langfuse_tracing(input_message: str) -> str:
    agency_instance = create_agency()

    @observe()
    async def get_response_wrapper(message: str):
        return await agency_instance.get_response(
            message=message,
        )

    response = await get_response_wrapper(input_message)
    return response.final_output


async def agentops_tracing(input_message: str) -> str:
    agentops.init(auto_start_session=True, trace_name="Agentops tracing", tags=["openai", "agentops-example"])
    tracer = agentops.start_trace(trace_name="Agentops tracing", tags=["openai", "agentops-example"])

    agency_instance = create_agency()
    response = await agency_instance.get_response(
        message=input_message,
    )
    agentops.end_trace(tracer, end_state="Success")
    return response.final_output


# ────────────────────────────────
# Entry point
# ────────────────────────────────
if __name__ == "__main__":
    test_message = "Create a function to calculate factorial and analyze the dataset [10, 25, 15, 30, 20]."

    print("Running OpenAI tracing...")
    print(asyncio.run(openai_tracing(test_message)))

    print("\nRunning Langfuse tracing...")
    print(asyncio.run(langfuse_tracing(test_message)))

    print("\nRunning AgentOps tracing...")
    print(asyncio.run(agentops_tracing(test_message)))

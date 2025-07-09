"""
Observability demo showing Langfuse and AgentOps tracing.

Run with: python examples/observability_demo.py
"""

import asyncio
import logging
import os
import sys
from typing import Any

from dotenv import load_dotenv

# Path setup for standalone examples
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

import agentops  # noqa: E402
from agents import ModelSettings, RunConfig, RunContextWrapper, function_tool, trace  # noqa: E402
from langfuse import observe  # noqa: E402
from pydantic import BaseModel, Field

from agency_swarm import Agency, Agent  # noqa: E402

load_dotenv()
logging.basicConfig(level=logging.INFO)


# ────────────────────────────────
# Tool definition
# ────────────────────────────────
class MySDKToolArgs(BaseModel):
    param1: str = Field(..., description="Test input for the tool. Does nothing")


@function_tool
async def test_tool(ctx: RunContextWrapper[Any], args: MySDKToolArgs) -> str:
    """Return a predictable ID."""
    return "Unique ID: 12332211"


# ────────────────────────────────
# Agency definition (agents + flows)
# ────────────────────────────────


def create_agency() -> Agency:
    """Create agency with CEO, Developer, and Analyst."""
    ceo = Agent(
        name="CEO",
        instructions="You are the CEO.",
        description="Manages projects and coordinates between team members",
        model="gpt-4.1",
        tools=[test_tool],
        model_settings=ModelSettings(temperature=0.3),
    )

    developer = Agent(
        name="Developer",
        instructions="You are the Developer.",
        description="Implements technical solutions and writes code",
        model="gpt-4.1",
        tools=[test_tool],
        model_settings=ModelSettings(temperature=0.3),
    )

    analyst = Agent(
        name="DataAnalyst",
        instructions="You are the Data Analyst.",
        description="Analyzes data and provides insights",
        model="gpt-4.1",
        tools=[test_tool],
        model_settings=ModelSettings(temperature=0.3),
    )

    return Agency(
        ceo,
        developer,
        analyst,
        communication_flows=[
            (ceo, developer),
            (ceo, analyst),
            (developer, analyst),
        ],
        temperature=0.01,
    )


# ────────────────────────────────
# Tracing wrappers
# ────────────────────────────────
async def openai_tracing(input_message: str) -> str:
    agency_instance = create_agency()
    with trace("Openai tracing"):
        response = await agency_instance.get_response(message=input_message)
    return response.final_output


@observe()
async def langfuse_tracing(input_message: str) -> str:
    agency_instance = create_agency()

    @observe()
    async def get_response_wrapper(message: str):
        return await agency_instance.get_response(
            message=message,
            run_config=RunConfig(tracing_disabled=True),
        )

    response = await get_response_wrapper(input_message)
    return response.final_output


async def agentops_tracing(input_message: str) -> str:
    agentops.init(auto_start_session=True, trace_name="Agentops tracing", tags=["openai", "agentops-example"])
    tracer = agentops.start_trace(trace_name="Agentops tracing", tags=["openai", "agentops-example"])

    agency_instance = create_agency()
    response = await agency_instance.get_response(message=input_message)
    agentops.end_trace(tracer, end_state="Success")
    return response.final_output


# ────────────────────────────────
# Entry point
# ────────────────────────────────
if __name__ == "__main__":
    msg = "Hi, use the test tool please."
    print(f"Agentops tracing: {asyncio.run(agentops_tracing(msg))}\n")

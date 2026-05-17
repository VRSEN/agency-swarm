"""
Agency Context Example

Simple demonstration of sharing data between agents using agency context.
Shows how one agent can store data and another can retrieve it.
"""

import asyncio
import logging
import os
import sys

# Path setup for standalone examples
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agency_swarm import Agency, Agent, MasterContext, RunContextWrapper, function_tool

# Minimal logging setup
logging.basicConfig(level=logging.WARNING)
logging.getLogger("agency_swarm").setLevel(logging.WARNING)

# --- Data Storage Tools --- #


@function_tool
async def store_customer_data(ctx: RunContextWrapper[MasterContext], customer_id: str, name: str) -> str:
    """Store customer information in agency context."""
    context: MasterContext = ctx.context

    customer_data = {"id": customer_id, "name": name, "status": "active"}

    context.set("customer_data", customer_data)
    return f"Stored customer data for {name} (ID: {customer_id})"


@function_tool
async def get_customer_data(ctx: RunContextWrapper[MasterContext]) -> str:
    """Retrieve customer information from agency context."""
    context: MasterContext = ctx.context

    customer_data = context.get("customer_data")
    if not customer_data:
        return "No customer data found. Please store customer data first."

    return f"Customer: {customer_data['name']} (ID: {customer_data['id']}, Status: {customer_data['status']})"


@function_tool
async def analyze_customer(ctx: RunContextWrapper[MasterContext]) -> str:
    """Analyze customer using data from agency context."""
    context: MasterContext = ctx.context

    customer_data = context.get("customer_data")
    if not customer_data:
        return "Cannot analyze - no customer data available."

    # Store analysis results
    analysis = {"customer_id": customer_data["id"], "risk_level": "low", "recommendation": "approved"}

    context.set("customer_analysis", analysis)
    return (
        f"Analysis complete for {customer_data['name']}: {analysis['recommendation']} (risk: {analysis['risk_level']})"
    )


@function_tool
async def show_context_summary(ctx: RunContextWrapper[MasterContext]) -> str:
    """Show what's currently stored in agency context."""
    context: MasterContext = ctx.context

    customer_data = context.get("customer_data")
    analysis = context.get("customer_analysis")

    summary = "Agency Context Summary:\n"

    if customer_data:
        summary += f"• Customer: {customer_data['name']} ({customer_data['id']})\n"
    else:
        summary += "• Customer: None\n"

    if analysis:
        summary += f"• Analysis: {analysis['recommendation']} ({analysis['risk_level']} risk)\n"
    else:
        summary += "• Analysis: None\n"

    return summary


# --- Agents --- #

data_agent = Agent(
    name="DataAgent",
    instructions="You handle customer data storage and retrieval. Use your tools to store and access customer information.",
    tools=[store_customer_data, get_customer_data, show_context_summary],
)

analyst_agent = Agent(
    name="AnalystAgent",
    instructions="You analyze customers using data stored by other agents. Access customer data from agency context.",
    tools=[analyze_customer, get_customer_data, show_context_summary],
)

# --- Agency Setup --- #

agency = Agency(
    data_agent,
    communication_flows=[data_agent > analyst_agent],
    user_context={"session_id": "demo_session", "system": "agency_context_demo"},
)

# --- Demo --- #


async def run_demo():
    """Demonstrate agency context sharing between agents."""
    print("Agency Context Demo")
    print("=" * 40)

    # Step 1: Store customer data
    print("\nStep 1: Storing customer data...")
    response1 = await agency.get_response(message="Please store customer data: ID 'CUST123', name 'Alice Johnson'")
    print(f"✅ {response1.final_output}")

    # Step 2: Delegate analysis to another agent
    print("\nStep 2: Asking data agent to delegate analysis...")
    response2 = await agency.get_response(
        message="Please ask the analyst agent to analyze the customer data I just stored."
    )
    print(f"✅ {response2.final_output}")

    # Step 3: Show final context state
    print("\nStep 3: Checking final agency context...")
    response3 = await agency.get_response(message="Show me a summary of what's currently stored in the agency context.")
    print(f"✅ {response3.final_output}")

    print("\nDemo complete!")


if __name__ == "__main__":
    asyncio.run(run_demo())

"""
Integration test for agency context sharing between agents.

This test verifies that agents can share data through the agency context,
ensuring that changes made by one agent are visible to other agents.
"""

import pytest
from agents import RunContextWrapper, function_tool

from agency_swarm import Agency, Agent, MasterContext


@function_tool
async def store_data(ctx: RunContextWrapper[MasterContext], key: str, value: str) -> str:
    """Store data in the shared context."""
    context: MasterContext = ctx.context
    context.set(key, value)
    return f"Stored {key}={value}"


@function_tool
async def get_data(ctx: RunContextWrapper[MasterContext], key: str) -> str:
    """Get data from the shared context."""
    context: MasterContext = ctx.context
    value = context.get(key)
    return f"Value for {key}: {value}"


@pytest.mark.asyncio
async def test_context_sharing_between_agents():
    """Test that data stored by one agent is accessible to another agent."""

    # Create agents
    agent1 = Agent(
        name="Agent1",
        instructions="You store data in the context.",
        tools=[store_data],
        model="gpt-5-mini",
    )

    agent2 = Agent(
        name="Agent2",
        instructions="You retrieve and store data in the context.",
        tools=[get_data, store_data],
        model="gpt-5-mini",
    )

    # Create agency with both agents as entry points
    agency = Agency(
        agent1,
        agent2,
        communication_flows=[agent1 > agent2],
        user_context={"initial": "test"},
    )

    # Agent1 stores data
    response1 = await agency.get_response(
        "Store 'shared_key' with value 'shared_value'",
        recipient_agent=agent1,
    )
    assert "shared_value" in response1.final_output

    # Verify data is in agency context
    assert agency.user_context.get("shared_key") == "shared_value"
    assert agency.user_context.get("initial") == "test"  # Original value preserved

    # Directly ask Agent2 to retrieve the data
    response2 = await agency.get_response(
        "Get the value for 'shared_key'",
        recipient_agent=agent2,
    )
    assert "shared_value" in response2.final_output

    # Agent2 can also store data that's visible to the agency
    await agency.get_response(
        "Store 'agent2_key' with value 'agent2_value'",
        recipient_agent=agent2,
    )

    # Verify Agent2's data is in agency context
    assert agency.user_context.get("agent2_key") == "agent2_value"
    assert agency.user_context.get("shared_key") == "shared_value"  # Previous data preserved

    # Retrieve Agent2's data directly from Agent2
    response4 = await agency.get_response(
        "Get the value for 'agent2_key'",
        recipient_agent=agent2,
    )
    assert "agent2_value" in response4.final_output

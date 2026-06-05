"""
Integration test for agency context sharing between agents.

This test verifies that agents can share data through run context,
ensuring callers can carry that state between agency calls.
"""

import pytest
from agents import ModelSettings, RunContextWrapper, function_tool

from agency_swarm import Agency, Agent, MasterContext
from tests.deterministic_model import DeterministicModel


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
        model=DeterministicModel(),
        model_settings=ModelSettings(tool_choice="required"),
        tool_use_behavior="stop_on_first_tool",
    )

    agent2 = Agent(
        name="Agent2",
        instructions="You retrieve and store data in the context.",
        tools=[get_data, store_data],
        model=DeterministicModel(),
        model_settings=ModelSettings(tool_choice="required"),
        tool_use_behavior="stop_on_first_tool",
    )

    agency = Agency(
        agent1,
        agent2,
        communication_flows=[agent1 > agent2],
    )

    session_context = {"initial": "test"}

    response1 = await agency.get_response(
        "Store shared_key with value shared_value",
        recipient_agent=agent1,
        context_override=session_context,
    )
    tool_outputs_1 = [item.output for item in response1.new_items if hasattr(item, "output")]
    assert any("Stored shared_key=shared_value" in str(output) for output in tool_outputs_1)

    session_context = response1.context_wrapper.context.user_context
    assert session_context["shared_key"] == "shared_value"
    assert session_context["initial"] == "test"

    response2 = await agency.get_response(
        "Get the value for shared_key",
        recipient_agent=agent2,
        context_override=session_context,
    )
    tool_outputs_2 = [item.output for item in response2.new_items if hasattr(item, "output")]
    assert any("Value for shared_key: shared_value" in str(output) for output in tool_outputs_2)

    response3 = await agency.get_response(
        "Store agent2_key with value agent2_value",
        recipient_agent=agent2,
        context_override=response2.context_wrapper.context.user_context,
    )

    session_context = response3.context_wrapper.context.user_context
    assert session_context["agent2_key"] == "agent2_value"
    assert session_context["shared_key"] == "shared_value"

    response4 = await agency.get_response(
        "Get the value for agent2_key",
        recipient_agent=agent2,
        context_override=session_context,
    )
    tool_outputs_4 = [item.output for item in response4.new_items if hasattr(item, "output")]
    assert any("Value for agent2_key: agent2_value" in str(output) for output in tool_outputs_4)


@pytest.mark.asyncio
async def test_context_override_is_shared_with_send_message_recipient():
    """Sub-agents called by send_message receive the caller's run context."""
    agent1 = Agent(
        name="Agent1",
        instructions="You delegate context reads to Agent2.",
        model=DeterministicModel(),
        model_settings=ModelSettings(tool_choice="required"),
    )
    agent2 = Agent(
        name="Agent2",
        instructions="You retrieve data from the context.",
        tools=[get_data],
        model=DeterministicModel(),
        model_settings=ModelSettings(tool_choice="required"),
        tool_use_behavior="stop_on_first_tool",
    )
    agency = Agency(agent1, communication_flows=[agent1 > agent2])

    response = await agency.get_response(
        "Ask Agent2 for the value for shared_key",
        recipient_agent=agent1,
        context_override={"shared_key": "shared_value"},
    )

    tool_outputs = [item.output for item in response.new_items if hasattr(item, "output")]
    assert any("Value for shared_key: shared_value" in str(output) for output in tool_outputs)

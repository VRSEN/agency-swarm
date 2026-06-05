"""
Integration test for context persistence across agent calls.

This test verifies that modifications to user_context can be carried
between agent invocations without storing state on the Agency.
"""

import pytest
from agents import ModelSettings, RunContextWrapper, function_tool

from agency_swarm import Agency, Agent, MasterContext
from tests.deterministic_model import DeterministicModel


@function_tool
async def store_data(ctx: RunContextWrapper[MasterContext], key: str, value: str) -> str:
    """Store a value in the shared context."""
    ctx.context.set(key, value)
    return f"Stored {key}={value}"


@function_tool
async def get_data(ctx: RunContextWrapper[MasterContext], key: str) -> str:
    """Read a value from the shared context."""
    value = ctx.context.get(key, "not_found")
    return f"Value for {key}: {value}"


@pytest.mark.asyncio
async def test_caller_owned_context_can_be_carried_between_calls():
    """Context changes persist when the caller passes the returned run context forward."""
    agent = Agent(
        name="ContextAgent",
        instructions="You store and retrieve data using the provided tools.",
        tools=[store_data, get_data],
        model=DeterministicModel(),
        model_settings=ModelSettings(tool_choice="required"),
        tool_use_behavior="stop_on_first_tool",
    )
    agency = Agency(agent)

    session_context = {"initial": "value"}
    response1 = await agency.get_response(
        "Store stored_key with value test_data",
        context_override=session_context,
    )

    tool_outputs = [item.output for item in response1.new_items if hasattr(item, "output")]
    assert any("Stored stored_key=test_data" in str(output) for output in tool_outputs)

    next_context = response1.context_wrapper.context.user_context
    response2 = await agency.get_response(
        "Read the value for stored_key",
        context_override=next_context,
    )

    tool_outputs2 = [item.output for item in response2.new_items if hasattr(item, "output")]
    assert any("Value for stored_key: test_data" in str(output) for output in tool_outputs2)
    assert response2.context_wrapper.context.user_context["initial"] == "value"

    with pytest.warns(DeprecationWarning, match=r"Agency\.user_context"):
        assert agency.user_context == {}


@pytest.mark.asyncio
async def test_deprecated_agency_user_context_is_only_an_initial_seed():
    """Deprecated agency user_context seeds a run but is not mutated by that run."""
    agent = Agent(
        name="TestAgent",
        instructions="You store and retrieve data using the provided tools.",
        tools=[store_data, get_data],
        model=DeterministicModel(),
        model_settings=ModelSettings(tool_choice="required"),
        tool_use_behavior="stop_on_first_tool",
    )

    with pytest.warns(DeprecationWarning, match=r"Agency\(user_context"):
        agency = Agency(agent, user_context={"agency_key": "agency_value"})

    response = await agency.get_response(
        "Store stored_key with value test_data",
        context_override={"override_key": "override_value"},
    )

    tool_outputs = [item.output for item in response.new_items if hasattr(item, "output")]
    assert any("Stored stored_key=test_data" in str(output) for output in tool_outputs)

    assert response.context_wrapper.context.user_context == {
        "agency_key": "agency_value",
        "override_key": "override_value",
        "stored_key": "test_data",
    }
    with pytest.warns(DeprecationWarning, match=r"Agency\.user_context"):
        assert agency.user_context == {"agency_key": "agency_value"}

"""
Integration test for context persistence across agent calls.

This test verifies that modifications to user_context are preserved
between different agent invocations within the same agency.
"""

import pytest
from pydantic import Field

from agency_swarm import Agency, Agent
from agency_swarm.tools import BaseTool


class StoreValueTool(BaseTool):
    """Store a value in the shared context."""

    key: str = Field(..., description="Key to store")
    value: str = Field(..., description="Value to store")

    def run(self):
        if self.context:
            self.context.set(self.key, self.value)
            return f"Stored {self.key}={self.value}"
        return "No context available"


class ReadValueTool(BaseTool):
    """Read a value from the shared context."""

    key: str = Field(..., description="Key to read")

    def run(self):
        if self.context:
            value = self.context.get(self.key, "not_found")
            return f"Value for {self.key}: {value}"
        return "No context available"


@pytest.mark.asyncio
async def test_context_persistence_between_calls():
    """Test that context changes persist between separate agent calls."""

    # Create agent with both tools
    agent = Agent(
        name="ContextAgent",
        instructions="You store and retrieve data using the provided tools.",
        tools=[StoreValueTool, ReadValueTool],
        model="gpt-5-mini",
    )

    # Create agency with initial context
    agency = Agency(
        agent,
        user_context={"initial": "value"},
    )

    # First call: Store a value
    response1 = await agency.get_response("Store the value 'test_data' with key 'stored_key' using StoreValueTool")

    # Verify the tool was called
    tool_outputs = [item.output for item in response1.new_items if hasattr(item, "output")]
    assert any("Stored stored_key=test_data" in str(output) for output in tool_outputs)

    # Second call: Read the value back
    response2 = await agency.get_response("Read the value for key 'stored_key' using ReadValueTool")

    # Verify the value was persisted
    tool_outputs2 = [item.output for item in response2.new_items if hasattr(item, "output")]
    assert any("Value for stored_key: test_data" in str(output) for output in tool_outputs2)

    # Verify agency context was updated
    assert agency.user_context.get("stored_key") == "test_data"
    assert agency.user_context.get("initial") == "value"  # Original value still there


@pytest.mark.asyncio
async def test_context_override_does_not_affect_agency():
    """Test that context_override doesn't modify the agency's user_context."""

    agent = Agent(
        name="TestAgent",
        instructions="You read data using ReadValueTool.",
        tools=[ReadValueTool],
        model="gpt-5-mini",
    )

    agency = Agency(
        agent,
        user_context={"agency_key": "agency_value"},
    )

    # Call with context override
    response = await agency.get_response(
        "Read the value for key 'override_key' using ReadValueTool", context_override={"override_key": "override_value"}
    )

    # Verify the override was used in the call
    tool_outputs = [item.output for item in response.new_items if hasattr(item, "output")]
    assert any("Value for override_key: override_value" in str(output) for output in tool_outputs)

    # Verify agency context was NOT modified
    assert "override_key" not in agency.user_context
    assert agency.user_context == {"agency_key": "agency_value"}

"""Integration test for BaseTool context support."""

import pytest
from pydantic import Field

from agency_swarm import Agency, Agent, BaseTool


class StoreDataTool(BaseTool):
    """Store data in agency context using BaseTool."""

    key: str = Field(..., description="Key to store data under")
    value: str = Field(..., description="Value to store")

    def run(self):
        if self._context is not None:
            # Access the MasterContext through the RunContextWrapper
            master_context = self._context.context
            master_context.set(self.key, self.value)
            return f"Stored {self.key}={self.value}"
        else:
            return "Error: No context available"


class RetrieveDataTool(BaseTool):
    """Retrieve data from agency context using BaseTool."""

    key: str = Field(..., description="Key to retrieve data for")

    def run(self):
        if self._context is not None:
            # Access the MasterContext through the RunContextWrapper
            master_context = self._context.context
            value = master_context.get(self.key, "not_found")
            return f"Retrieved {self.key}={value}"
        else:
            return "Error: No context available"


@pytest.mark.asyncio
async def test_basetool_context_integration():
    """Test that BaseTools can access agency context."""

    class ContextReaderTool(BaseTool):
        """A tool that reads from context."""

        key: str = Field(..., description="Key to read from context")

        def run(self):
            if self._context is not None:
                value = self._context.context.user_context.get(self.key, "not_found")
                return f"Context value for {self.key}: {value}"
            else:
                return "No context available"

    # Create agent with context reader tool
    agent = Agent(
        name="ContextAgent",
        instructions="You read data from context using the ContextReaderTool.",
        tools=[ContextReaderTool],
        model="gpt-4o-mini",
    )

    # Create agency with initial context
    agency = Agency(
        agent,
        user_context={"test_key": "test_value", "another_key": "another_value"},
    )

    # Test reading from context
    response = await agency.get_response("Read the value of test_key using ContextReaderTool", recipient_agent=agent)

    # Check that the tool was called and returned the correct value
    tool_outputs = [item.output for item in response.new_items if hasattr(item, "output")]
    assert any("Context value for test_key: test_value" in str(output) for output in tool_outputs)


@pytest.mark.asyncio
async def test_basetool_async_context():
    """Test that async BaseTools also receive context."""

    class AsyncContextTool(BaseTool):
        """An async tool that uses context."""

        data: str = Field(..., description="Data to process")

        async def run(self):
            if self._context is not None:
                ctx_data = self._context.context.user_context.get("async_key", "default")
                return f"Async processed: {self.data} with context: {ctx_data}"
            else:
                return f"Async processed: {self.data} without context"

    agent = Agent(
        name="AsyncAgent",
        instructions="You process data asynchronously.",
        tools=[AsyncContextTool],
        model="gpt-4o-mini",
    )

    agency = Agency(
        agent,
        user_context={"async_key": "async_value"},
    )

    response = await agency.get_response("Process 'test_data' using AsyncContextTool")
    assert "Async processed: test_data with context: async_value" in response.final_output

"""
Tests for multi-agency agent support.

This module tests the ability for a single agent to be registered
in multiple agencies without context leakage between them.
"""

import asyncio
from typing import Literal

import pytest
from pydantic import Field

from agency_swarm import Agency, Agent
from agency_swarm.tools import BaseTool


class SharedStateTool(BaseTool):
    """Tool that uses shared state to test context isolation."""

    value: str = Field(..., description="Value to store or retrieve")
    action: Literal["set", "get"] = Field(..., description="Either 'set' or 'get'")

    def run(self):
        """Execute the tool action."""
        print(f"Shared state: {self.context}")
        if self.action == "set":
            self.context.set("test_value", self.value)
            print(f"Set test_value to: {self.value}")
            return f"Set test_value to: {self.value}"
        elif self.action == "get":
            stored_value = self.context.get("test_value", "NOT_SET")
            print(f"Current test_value: {stored_value}")
            return f"Current test_value: {stored_value}"


@pytest.fixture
def shared_agent():
    """Create an agent that will be shared between multiple agencies."""
    return Agent(
        name="SharedAgent",
        instructions="You are a shared agent that can set and get values using the SharedStateTool.",
        tools=[SharedStateTool],
    )


@pytest.fixture
def agency1(shared_agent):
    """Create the first agency."""
    assistant1 = Agent(name="Assistant1", instructions="You are Assistant1 in Agency1")

    agency = Agency(
        shared_agent,
        assistant1,
        communication_flows=[shared_agent > assistant1],
        name="Agency1",
        user_context={"agency_name": "Agency1", "test_data": "agency1_data"},
    )
    return agency


@pytest.fixture
def agency2(shared_agent):
    """Create the second agency using the same shared agent."""
    assistant2 = Agent(name="Assistant2", instructions="You are Assistant2 in Agency2")

    agency = Agency(
        shared_agent,
        assistant2,
        communication_flows=[shared_agent > assistant2],
        name="Agency2",
        user_context={"agency_name": "Agency2", "test_data": "agency2_data"},
    )
    return agency


class TestMultiAgencySupport:
    """Test cases for multi-agency agent support."""

    @pytest.mark.asyncio
    async def test_agent_can_be_registered_in_multiple_agencies(self, shared_agent, agency1, agency2):
        """Test that a single agent can be registered in multiple agencies."""
        # Verify the agent is registered in both agencies
        assert shared_agent.name in agency1.agents
        assert shared_agent.name in agency2.agents
        assert id(agency1.agents["SharedAgent"]) == id(shared_agent)
        assert id(agency2.agents["SharedAgent"]) == id(shared_agent)

        # Verify each agency has its own context for the shared agent
        context1 = agency1._get_agent_context("SharedAgent")
        context2 = agency2._get_agent_context("SharedAgent")

        # Verify contexts are different and isolated
        assert context1.agency_instance is agency1
        assert context2.agency_instance is agency2
        assert context1.thread_manager is not context2.thread_manager

    @pytest.mark.asyncio
    async def test_thread_manager_isolation(self, shared_agent, agency1, agency2):
        """Test that thread managers are isolated between agencies."""
        # Get responses from both agencies
        await agency1.get_response("Set test_value to 'agency1_value' using the SharedStateTool")
        await agency2.get_response("Set test_value to 'agency2_value' using the SharedStateTool")

        # Get agency contexts for the shared agent
        context1 = agency1._get_agent_context("SharedAgent")
        context2 = agency2._get_agent_context("SharedAgent")

        assert context1.thread_manager is not context2.thread_manager

        # Verify thread isolation by checking message counts
        messages1 = context1.thread_manager.get_all_messages()
        messages2 = context2.thread_manager.get_all_messages()

        # Each agency should have its own conversation history
        agency1_messages = [m for m in messages1 if m.get("agent") == "SharedAgent"]
        agency2_messages = [m for m in messages2 if m.get("agent") == "SharedAgent"]

        assert len(agency1_messages) > 0
        assert len(agency2_messages) > 0

        # Messages should be different between agencies
        assert messages1 != messages2

    @pytest.mark.asyncio
    async def test_context_isolation_between_agencies(self, shared_agent, agency1, agency2):
        """Test that MasterContext is isolated between agencies."""
        # Set values in agency1
        await agency1.get_response("Use SharedStateTool to set test_value to 'agency1_secret'")

        # Get value in agency2 - should not see agency1's value
        response2 = await agency2.get_response("Use SharedStateTool to get the current test_value")

        # The value should be isolated - agency2 shouldn't see agency1's value
        assert "agency1_secret" not in str(response2.final_output)

        # Set different value in agency2
        await agency2.get_response("Use SharedStateTool to set test_value to 'agency2_secret'")

        # Verify agency1 still has its own value
        response1 = await agency1.get_response("Use SharedStateTool to get the current test_value")
        assert "agency1_secret" in str(response1.final_output)
        assert "agency2_secret" not in str(response1.final_output)

    @pytest.mark.asyncio
    async def test_subagent_registration_isolation(self, shared_agent, agency1, agency2):
        """Test that subagent registration is isolated between agencies."""
        # Get agency contexts for the shared agent
        context1 = agency1._get_agent_context("SharedAgent")
        context2 = agency2._get_agent_context("SharedAgent")

        # Each agency should have different subagents
        subagents1 = context1.subagents
        subagents2 = context2.subagents

        # Verify subagent isolation
        assert "Assistant1" in subagents1
        assert "Assistant1" not in subagents2
        assert "Assistant2" in subagents2
        assert "Assistant2" not in subagents1

    @pytest.mark.asyncio
    async def test_user_context_isolation(self, shared_agent, agency1, agency2):
        """Test that user context is isolated between agencies."""
        # Verify each agency has its own user context
        assert agency1.user_context["agency_name"] == "Agency1"
        assert agency1.user_context["test_data"] == "agency1_data"

        assert agency2.user_context["agency_name"] == "Agency2"
        assert agency2.user_context["test_data"] == "agency2_data"

        # User contexts should be different
        assert agency1.user_context != agency2.user_context

    @pytest.mark.asyncio
    async def test_concurrent_agency_operations(self, shared_agent, agency1, agency2):
        """Test concurrent operations on the same agent from different agencies (now safe with stateless design)."""
        # Run concurrent operations - this should be safe with stateless context passing
        import asyncio

        task1 = asyncio.create_task(agency1.get_response("Use SharedStateTool to set test_value to 'concurrent1'"))
        task2 = asyncio.create_task(agency2.get_response("Use SharedStateTool to set test_value to 'concurrent2'"))

        # Wait for both to complete
        response1, response2 = await asyncio.gather(task1, task2)

        # Both should complete successfully with no race conditions
        assert response1.final_output is not None
        assert response2.final_output is not None

        # Verify context isolation after concurrent operations
        get_task1 = asyncio.create_task(agency1.get_response("Use SharedStateTool to get the current test_value"))
        get_task2 = asyncio.create_task(agency2.get_response("Use SharedStateTool to get the current test_value"))

        get_response1, get_response2 = await asyncio.gather(get_task1, get_task2)

        # Each should have its own value (context isolation maintained)
        assert "concurrent1" in str(get_response1.final_output)
        assert "concurrent2" in str(get_response2.final_output)

    @pytest.mark.asyncio
    async def test_streaming_context_isolation(self, shared_agent, agency1, agency2):
        """Test that streaming responses maintain context isolation."""
        # Test streaming from agency1
        events1 = []
        async for event in agency1.get_response_stream("Use SharedStateTool to set test_value to 'stream1'"):
            events1.append(event)

        # Test streaming from agency2
        events2 = []
        async for event in agency2.get_response_stream("Use SharedStateTool to set test_value to 'stream2'"):
            events2.append(event)

        # Both streams should complete
        assert len(events1) > 0
        assert len(events2) > 0

        # Verify context isolation after streaming
        response1 = await agency1.get_response("Use SharedStateTool to get the current test_value")
        response2 = await agency2.get_response("Use SharedStateTool to get the current test_value")

        # Should have different values
        output1 = str(response1.final_output)
        output2 = str(response2.final_output)
        assert "stream1" in output1
        assert "stream2" in output2
        assert output1 != output2


class TestStatelessContextPassing:
    """Test cases for stateless context passing functionality."""

    @pytest.mark.asyncio
    async def test_context_isolation_during_concurrent_execution(self, shared_agent, agency1, agency2):
        """Test that contexts remain isolated during concurrent execution."""
        # Execute in both agencies concurrently - this should work without race conditions
        # because contexts are passed statlessly

        task1 = asyncio.create_task(agency1.get_response("Hello from Agency1"))
        task2 = asyncio.create_task(agency2.get_response("Hello from Agency2"))

        # Both should complete successfully without interference
        response1, response2 = await asyncio.gather(task1, task2)

        assert response1.final_output is not None
        assert response2.final_output is not None

    def test_context_factory_validation(self, shared_agent, agency1, agency2):
        """Test that context factory pattern works correctly."""
        # Each agency should have its own context for the shared agent
        context1 = agency1._get_agent_context("SharedAgent")
        context2 = agency2._get_agent_context("SharedAgent")

        # Contexts should be different instances
        assert context1 is not context2
        assert context1.agency_instance is agency1
        assert context2.agency_instance is agency2

        # Invalid agent name should raise error
        with pytest.raises(ValueError, match="No context found for agent"):
            agency1._get_agent_context("NonexistentAgent")

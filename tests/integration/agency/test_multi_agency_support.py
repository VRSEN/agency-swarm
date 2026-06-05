"""
Tests for multi-agency agent support.

This module tests the ability for a single agent to be registered
in multiple agencies without context leakage between them.
"""

import asyncio
from typing import Literal

import pytest
from agents import ModelSettings, RunResult
from agents.items import ToolCallOutputItem
from pydantic import Field

from agency_swarm import Agency, Agent
from agency_swarm.tools import BaseTool
from tests.deterministic_model import DeterministicModel


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


def _tool_outputs(response: RunResult) -> list[str]:
    return [str(item.output) for item in response.new_items if isinstance(item, ToolCallOutputItem)]


def _assert_tool_output_contains(response: RunResult, expected: str) -> None:
    tool_outputs = _tool_outputs(response)
    assert any(expected in output for output in tool_outputs), f"Expected {expected!r} in tool outputs: {tool_outputs}"


def _assert_tool_output_excludes(response: RunResult, unexpected: str) -> None:
    tool_outputs = _tool_outputs(response)
    assert all(unexpected not in output for output in tool_outputs), (
        f"Did not expect {unexpected!r} in tool outputs: {tool_outputs}"
    )


@pytest.fixture
def shared_agent():
    """Create an agent that will be shared between multiple agencies."""
    return Agent(
        name="SharedAgent",
        instructions="You are a shared agent that can set and get values using the SharedStateTool.",
        tools=[SharedStateTool],
        model=DeterministicModel(),
        model_settings=ModelSettings(tool_choice="required"),
        tool_use_behavior="stop_on_first_tool",
    )


@pytest.fixture
def agency1(shared_agent):
    """Create the first agency."""
    assistant1 = Agent(
        name="Assistant1",
        instructions="You are Assistant1 in Agency1",
        model=DeterministicModel(),
    )

    agency = Agency(
        shared_agent,
        assistant1,
        communication_flows=[shared_agent > assistant1],
        name="Agency1",
    )
    return agency


@pytest.fixture
def agency2(shared_agent):
    """Create the second agency using the same shared agent."""
    assistant2 = Agent(
        name="Assistant2",
        instructions="You are Assistant2 in Agency2",
        model=DeterministicModel(),
    )

    agency = Agency(
        shared_agent,
        assistant2,
        communication_flows=[shared_agent > assistant2],
        name="Agency2",
    )
    return agency


@pytest.fixture
def agency1_context():
    """Create caller-owned context for the first agency."""
    return {"agency_name": "Agency1", "test_data": "agency1_data"}


@pytest.fixture
def agency2_context():
    """Create caller-owned context for the second agency."""
    return {"agency_name": "Agency2", "test_data": "agency2_data"}


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
        context1 = agency1.get_agent_context("SharedAgent")
        context2 = agency2.get_agent_context("SharedAgent")

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
        context1 = agency1.get_agent_context("SharedAgent")
        context2 = agency2.get_agent_context("SharedAgent")

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
    async def test_context_isolation_between_agencies(
        self, shared_agent, agency1, agency2, agency1_context, agency2_context
    ):
        """Test that MasterContext is isolated between agencies."""
        response_set_1 = await agency1.get_response(
            "Use SharedStateTool to set test_value to 'agency1_secret'",
            context_override=agency1_context,
        )
        agency1_context = response_set_1.context_wrapper.context.user_context

        response2 = await agency2.get_response(
            "Use SharedStateTool to get the current test_value",
            context_override=agency2_context,
        )

        _assert_tool_output_excludes(response2, "agency1_secret")

        response_set_2 = await agency2.get_response(
            "Use SharedStateTool to set test_value to 'agency2_secret'",
            context_override=response2.context_wrapper.context.user_context,
        )

        response1 = await agency1.get_response(
            "Use SharedStateTool to get the current test_value",
            context_override=agency1_context,
        )
        _assert_tool_output_contains(response1, "agency1_secret")
        _assert_tool_output_excludes(response1, "agency2_secret")
        assert response_set_2.context_wrapper.context.user_context["test_value"] == "agency2_secret"

    @pytest.mark.asyncio
    async def test_subagent_registration_isolation(self, shared_agent, agency1, agency2):
        """Test that subagent registration is isolated between agencies."""
        # Get agency contexts for the shared agent
        context1 = agency1.get_agent_context("SharedAgent")
        context2 = agency2.get_agent_context("SharedAgent")

        # Each agency should have different subagents
        subagents1 = context1.subagents
        subagents2 = context2.subagents

        # Verify subagent isolation
        assert "Assistant1" in subagents1
        assert "Assistant1" not in subagents2
        assert "Assistant2" in subagents2
        assert "Assistant2" not in subagents1

    @pytest.mark.asyncio
    async def test_user_context_isolation(self, shared_agent, agency1, agency2, agency1_context, agency2_context):
        """Test that caller-owned user context is isolated between agencies."""
        assert agency1_context["agency_name"] == "Agency1"
        assert agency1_context["test_data"] == "agency1_data"
        assert agency2_context["agency_name"] == "Agency2"
        assert agency2_context["test_data"] == "agency2_data"
        assert agency1_context != agency2_context

    @pytest.mark.asyncio
    async def test_concurrent_agency_operations(self, shared_agent, agency1, agency2, agency1_context, agency2_context):
        """Test concurrent operations on the same agent from different agencies (now safe with stateless design)."""
        import asyncio

        task1 = asyncio.create_task(
            agency1.get_response(
                "Use SharedStateTool to set test_value to 'concurrent1'", context_override=agency1_context
            )
        )
        task2 = asyncio.create_task(
            agency2.get_response(
                "Use SharedStateTool to set test_value to 'concurrent2'", context_override=agency2_context
            )
        )

        response1, response2 = await asyncio.gather(task1, task2)

        assert response1.final_output is not None
        assert response2.final_output is not None
        assert response1.context_wrapper.context.user_context["test_value"] == "concurrent1"
        assert response2.context_wrapper.context.user_context["test_value"] == "concurrent2"

    @pytest.mark.asyncio
    async def test_streaming_context_isolation(self, shared_agent, agency1, agency2, agency1_context, agency2_context):
        """Test that streaming responses maintain context isolation."""
        events1 = []
        stream1 = agency1.get_response_stream(
            "Use SharedStateTool to set test_value to 'stream1'",
            context_override=agency1_context,
        )
        async for event in stream1:
            events1.append(event)

        events2 = []
        stream2 = agency2.get_response_stream(
            "Use SharedStateTool to set test_value to 'stream2'",
            context_override=agency2_context,
        )
        async for event in stream2:
            events2.append(event)

        assert len(events1) > 0
        assert len(events2) > 0
        assert stream1.final_result is not None
        assert stream2.final_result is not None

        stream_context_1 = stream1.final_result.context_wrapper.context.user_context
        stream_context_2 = stream2.final_result.context_wrapper.context.user_context

        assert stream_context_1["agency_name"] == "Agency1"
        assert stream_context_2["agency_name"] == "Agency2"
        assert stream_context_1["test_data"] == "agency1_data"
        assert stream_context_2["test_data"] == "agency2_data"
        assert stream_context_1 != stream_context_2


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
        context1 = agency1.get_agent_context("SharedAgent")
        context2 = agency2.get_agent_context("SharedAgent")

        # Contexts should be different instances
        assert context1 is not context2
        assert context1.agency_instance is agency1
        assert context2.agency_instance is agency2

        # Invalid agent name should raise error
        with pytest.raises(ValueError, match="No context found for agent"):
            agency1.get_agent_context("NonexistentAgent")

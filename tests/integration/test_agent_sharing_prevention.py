"""
Integration test for agent sharing prevention between agencies.

Ensures that agent instances cannot be shared between multiple agencies
to prevent callback and ThreadManager conflicts.
"""

import pytest

from agency_swarm import Agency, Agent


class TestAgentSharingPrevention:
    """Test cases for agent sharing prevention between agencies."""

    def test_prevent_agent_sharing_between_agencies(self):
        """Test that sharing the same agent instance between agencies raises an error."""
        # Create a single agent instance
        shared_agent = Agent(
            name="SharedAgent",
            instructions="You are a shared agent",
        )

        # Create first agency with the agent - this should work
        agency1 = Agency(
            shared_agent,
            name="agency1",
        )

        # Verify agent is properly registered in agency1
        assert "SharedAgent" in agency1.agents
        assert agency1.agents["SharedAgent"] is shared_agent

        # Attempt to create second agency with same agent instance - this should fail
        with pytest.raises(ValueError) as exc_info:
            Agency(
                shared_agent,  # Same instance!
                name="agency2",
            )

        # Verify the error message is helpful
        error_msg = str(exc_info.value)
        assert "Agent 'SharedAgent' is already registered in agency 'agency1'" in error_msg
        assert "Each agent instance can only belong to one agency" in error_msg
        assert "create separate agent instances" in error_msg

    def test_allow_same_agent_in_same_agency(self):
        """Test that the same agent can be used multiple times in the same agency."""
        agent = Agent(
            name="TestAgent",
            instructions="You are a test agent",
        )

        # Using the same agent multiple times in agency_chart should work
        agency = Agency(
            agent,  # Entry point
            communication_flows=[(agent, agent)],  # Self-communication
            name="test_agency",
        )

        # Should not raise error and agent should be registered once
        assert "TestAgent" in agency.agents
        assert agency.agents["TestAgent"] is agent

    def test_separate_agent_instances_work(self):
        """Test that separate agent instances with same name can be used in different agencies."""
        # Create two separate agent instances with the same name and config
        agent1 = Agent(
            name="SameName",
            instructions="You are agent instance 1",
        )

        agent2 = Agent(
            name="SameName",
            instructions="You are agent instance 2",
        )

        # Each should be able to be used in a different agency
        agency1 = Agency(
            agent1,
            name="agency1",
        )

        agency2 = Agency(
            agent2,
            name="agency2",
        )

        # Verify both agencies work and have their own agent instances
        assert agency1.agents["SameName"] is agent1
        assert agency2.agents["SameName"] is agent2
        assert agent1 is not agent2  # Different instances

    def test_agent_sharing_with_callbacks(self):
        """Test the specific bug scenario with callbacks that was reported."""
        # Create agent
        ceo = Agent(
            name="CEO",
            instructions="You are a CEO",
        )

        # Create first agency without callbacks - this should work
        _ = Agency(
            ceo,
            name="agency1",
        )

        # Dummy callbacks for testing
        def load_callback(thread_id: str):
            return None

        def save_callback(thread_dict: dict):
            pass

        # Attempt to create second agency with same agent and callbacks - should fail
        with pytest.raises(ValueError) as exc_info:
            Agency(
                ceo,  # Same instance!
                load_threads_callback=load_callback,
                save_threads_callback=save_callback,
                name="agency2",
            )

        # Verify error message
        error_msg = str(exc_info.value)
        assert "Agent 'CEO' is already registered in agency 'agency1'" in error_msg

    @pytest.mark.asyncio
    async def test_agency_works_after_prevented_sharing(self):
        """Test that the original agency still works after preventing sharing."""
        agent = Agent(
            name="WorkingAgent",
            instructions="You are a working agent",
        )

        # Create first agency
        agency1 = Agency(
            agent,
            name="agency1",
        )

        # Try to create second agency (should fail)
        with pytest.raises(ValueError):
            Agency(
                agent,
                name="agency2",
            )

        # Original agency should still work
        try:
            result = await agency1.get_response("Hello", "WorkingAgent")
            # If we get here without error, the agency is still functional
            assert result is not None
        except Exception as e:
            pytest.fail(f"Agency1 should still be functional after preventing sharing: {e}")

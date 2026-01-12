"""
Unit tests for AgentFlow integration with Agency class.

Tests the parsing and handling of AgentFlow objects in communication_flows.
"""

import pytest

from agency_swarm import Agency, Agent
from agency_swarm.tools.send_message import Handoff, SendMessage, SendMessageHandoff


class CustomSendMessage(SendMessage):
    """Custom send message tool for testing."""

    pass


# --- Agency Integration Tests ---


def test_agency_with_mixed_communication_flows():
    """Test Agency with mixed communication flow formats."""
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5-mini")
    agent3 = Agent(name="Agent3", instructions="Test agent 3", model="gpt-5-mini")
    agent4 = Agent(name="Agent4", instructions="Test agent 4", model="gpt-5-mini")

    agency = Agency(
        agent1,
        communication_flows=[
            (agent1 > agent2 > agent3, CustomSendMessage),  # Chain with tool
            (agent1, agent4),  # Basic pair
            (agent2, agent4, Handoff),  # Pair with tool
        ],
    )

    assert len(agency.agents) == 4

    # Check tool mappings
    tool_mappings = agency._communication_tool_classes
    assert tool_mappings[("Agent1", "Agent2")] == CustomSendMessage
    assert tool_mappings[("Agent2", "Agent3")] == CustomSendMessage
    assert tool_mappings[("Agent2", "Agent4")] == Handoff


def test_agency_with_mixed_communication_flows_reverse():
    """Test Agency with reverse communication flow."""
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5-mini")
    agent3 = Agent(name="Agent3", instructions="Test agent 3", model="gpt-5-mini")

    agency = Agency(
        agent1,
        communication_flows=[
            (agent3 < agent2 < agent1, CustomSendMessage),  # Chain with tool
        ],
    )

    assert len(agency.agents) == 3

    # Check tool mappings
    tool_mappings = agency._communication_tool_classes
    assert tool_mappings[("Agent1", "Agent2")] == CustomSendMessage
    assert tool_mappings[("Agent2", "Agent3")] == CustomSendMessage


def test_duplicate_flow_detection_with_chains():
    """Test that duplicate flows are detected with AgentFlow chains."""
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5-mini")
    agent3 = Agent(name="Agent3", instructions="Test agent 3", model="gpt-5-mini")

    with pytest.raises(ValueError, match="Duplicate communication flow detected"):
        Agency(
            agent1,
            communication_flows=[
                (agent1 > agent2 > agent3, CustomSendMessage),  # Creates agent1->agent2
                (agent1, agent2),  # Duplicate agent1->agent2
            ],
        )


def test_agent_flow_with_handoff_tool():
    """Test that Handoff works with AgentFlow."""
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5-mini")
    agent3 = Agent(name="Agent3", instructions="Test agent 3", model="gpt-5-mini")

    # This should work without errors
    agency = Agency(
        agent1,
        communication_flows=[
            (agent1 > agent2 > agent3, Handoff),
        ],
    )

    assert len(agency.agents) == 3

    runtime_state1 = agency.get_agent_runtime_state("Agent1")
    runtime_state2 = agency.get_agent_runtime_state("Agent2")

    handoff_names_1 = [handoff.tool_name for handoff in runtime_state1.handoffs]
    handoff_names_2 = [handoff.tool_name for handoff in runtime_state2.handoffs]

    assert "transfer_to_Agent2" in handoff_names_1
    assert "transfer_to_Agent3" in handoff_names_2
    assert not agency.get_agent_runtime_state("Agent3").handoffs


def test_send_message_handoff_name_is_deprecated() -> None:
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5-mini")

    with pytest.deprecated_call(match=r"SendMessageHandoff is deprecated; use Handoff instead\."):
        Agency(
            agent1,
            communication_flows=[
                (agent1 > agent2, SendMessageHandoff),
            ],
        )

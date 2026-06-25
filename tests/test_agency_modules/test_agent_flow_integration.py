"""
Unit tests for AgentFlow integration with Agency class.

Tests the parsing and handling of AgentFlow objects in communication_flows.
"""

from typing import Any

import pytest

from agency_swarm import Agency, Agent
from agency_swarm.agent.context_types import AgentRuntimeState
from agency_swarm.agent.execution_helpers import cleanup_execution, prepare_master_context, setup_execution
from agency_swarm.tools.send_message import Handoff, SendMessage, SendMessageHandoff


class CustomSendMessage(SendMessage):
    """Custom send message tool for testing."""

    pass


class OtherCustomSendMessage(SendMessage):
    """Second custom send message tool for duplicate-family testing."""

    pass


class UnsupportedCommunicationTool:
    """Tool class outside the supported communication families."""

    pass


class CustomHandoff(Handoff):
    """Handoff variant with a distinct tool name."""

    def create_handoff(self, recipient_agent: Agent) -> Any:
        handoff = super().create_handoff(recipient_agent)
        handoff.tool_name = f"custom_transfer_to_{recipient_agent.name.replace(' ', '_')}"
        return handoff


class DefaultNamedCustomHandoff(Handoff):
    """Handoff variant that keeps the default tool name."""

    pass


class OtherDefaultNamedCustomHandoff(Handoff):
    """Second handoff variant that keeps the default tool name."""

    pass


class BrokenHandoff(Handoff):
    """Handoff variant that fails while wiring."""

    def create_handoff(self, recipient_agent: Agent) -> Any:
        _ = recipient_agent
        raise RuntimeError("broken handoff")


# --- Agency Integration Tests ---


def test_agency_with_mixed_communication_flows():
    """Test Agency with mixed communication flow formats."""
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5.4-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5.4-mini")
    agent3 = Agent(name="Agent3", instructions="Test agent 3", model="gpt-5.4-mini")
    agent4 = Agent(name="Agent4", instructions="Test agent 4", model="gpt-5.4-mini")

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
    assert tool_mappings[("Agent1", "Agent2")] == [CustomSendMessage]
    assert tool_mappings[("Agent2", "Agent3")] == [CustomSendMessage]
    assert tool_mappings[("Agent2", "Agent4")] == [Handoff]


def test_agency_with_mixed_communication_flows_reverse():
    """Test Agency with reverse communication flow."""
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5.4-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5.4-mini")
    agent3 = Agent(name="Agent3", instructions="Test agent 3", model="gpt-5.4-mini")

    agency = Agency(
        agent1,
        communication_flows=[
            (agent3 < agent2 < agent1, CustomSendMessage),  # Chain with tool
        ],
    )

    assert len(agency.agents) == 3

    # Check tool mappings
    tool_mappings = agency._communication_tool_classes
    assert tool_mappings[("Agent1", "Agent2")] == [CustomSendMessage]
    assert tool_mappings[("Agent2", "Agent3")] == [CustomSendMessage]


def test_agent_pair_can_use_send_message_and_handoff():
    """Test that one agent pair can expose both SendMessage and Handoff."""
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5.4-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5.4-mini")

    agency = Agency(
        agent1,
        communication_flows=[
            (agent1, agent2),
            (agent1 > agent2, Handoff),
        ],
    )

    assert agency._communication_tool_classes[("Agent1", "Agent2")] == [Handoff]
    assert ("Agent1", "Agent2") in agency._default_communication_tool_pairs

    runtime_state = agency.get_agent_runtime_state("Agent1")
    assert "agent2" in runtime_state.subagents
    assert "SendMessage" in runtime_state.send_message_tools

    handoff_names = [handoff.tool_name for handoff in runtime_state.handoffs]
    assert "transfer_to_Agent2" in handoff_names


@pytest.mark.parametrize("tool_mapping", ([Handoff], Handoff))
def test_legacy_two_value_flow_parser_patch_still_initializes_agency(monkeypatch, tool_mapping):
    """Test compatibility with OpenSwarm projects that patch parse_agent_flows."""
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5.4-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5.4-mini")

    def parse_agent_flows_legacy(_agency: Agency, _flows: list[Any]):
        return [(agent1, agent2)], {("Agent1", "Agent2"): tool_mapping}

    monkeypatch.setattr("agency_swarm.agency.core.parse_agent_flows", parse_agent_flows_legacy)

    agency = Agency(agent1, communication_flows=[(agent1 > agent2, Handoff)])

    assert agency._communication_tool_classes[("Agent1", "Agent2")] == [Handoff]
    assert agency._default_communication_tool_pairs == set()
    handoff_names = [handoff.tool_name for handoff in agency.get_agent_runtime_state("Agent1").handoffs]
    assert handoff_names == ["transfer_to_Agent2"]


def test_runtime_registration_keeps_multiple_send_message_tool_classes() -> None:
    """Test runtime registration creates each requested SendMessage class for one recipient."""
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5.4-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5.4-mini")
    runtime_state = AgentRuntimeState()

    agent1.register_subagent(agent2, send_message_tool_class=CustomSendMessage, runtime_state=runtime_state)
    agent1.register_subagent(agent2, send_message_tool_class=OtherCustomSendMessage, runtime_state=runtime_state)

    assert runtime_state.subagents == {"agent2": agent2}
    assert set(runtime_state.send_message_tools) == {"CustomSendMessage", "OtherCustomSendMessage"}
    assert isinstance(runtime_state.send_message_tools["CustomSendMessage"], CustomSendMessage)
    assert isinstance(runtime_state.send_message_tools["OtherCustomSendMessage"], OtherCustomSendMessage)


def test_runtime_handoff_variant_is_preserved_with_static_handoff() -> None:
    """Test runtime handoff variants are not dropped when a static handoff targets the same agent."""
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5.4-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5.4-mini")
    agent1.handoffs.append(Handoff().create_handoff(recipient_agent=agent2))

    agency = Agency(
        agent1,
        communication_flows=[
            (agent1, agent2, CustomHandoff),
        ],
    )

    context = agency.get_agent_context("Agent1")
    master_context = prepare_master_context(agent1, None, context)
    original_instructions = setup_execution(agent1, None, context, None)

    try:
        handoff_names = [handoff.tool_name for handoff in agent1.handoffs]
        assert handoff_names == ["transfer_to_Agent2", "custom_transfer_to_Agent2"]
    finally:
        cleanup_execution(agent1, original_instructions, None, context, master_context)


def test_same_name_handoff_variants_are_preserved_with_static_handoff() -> None:
    """Test distinct handoff classes are preserved even when they share one tool name."""
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5.4-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5.4-mini")
    agent1.handoffs.append(Handoff().create_handoff(recipient_agent=agent2))

    agency = Agency(
        agent1,
        communication_flows=[
            (agent1, agent2, [DefaultNamedCustomHandoff, OtherDefaultNamedCustomHandoff]),
        ],
    )

    context = agency.get_agent_context("Agent1")
    master_context = prepare_master_context(agent1, None, context)
    original_instructions = setup_execution(agent1, None, context, None)

    try:
        handoff_names = [handoff.tool_name for handoff in agent1.handoffs]
        assert handoff_names == ["transfer_to_Agent2", "transfer_to_Agent2", "transfer_to_Agent2"]
    finally:
        cleanup_execution(agent1, original_instructions, None, context, master_context)


def test_same_base_handoff_is_deduplicated_with_static_handoff() -> None:
    """Test the same base handoff is not duplicated when static and runtime sources overlap."""
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5.4-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5.4-mini")
    agent1.handoffs.append(Handoff().create_handoff(recipient_agent=agent2))

    agency = Agency(
        agent1,
        communication_flows=[
            (agent1, agent2, Handoff),
        ],
    )

    context = agency.get_agent_context("Agent1")
    master_context = prepare_master_context(agent1, None, context)
    original_instructions = setup_execution(agent1, None, context, None)

    try:
        handoff_names = [handoff.tool_name for handoff in agent1.handoffs]
        assert handoff_names == ["transfer_to_Agent2"]
    finally:
        cleanup_execution(agent1, original_instructions, None, context, master_context)


def test_later_communication_tool_is_wired_after_handoff_failure() -> None:
    """Test one broken tool class does not prevent later configured tools from wiring."""
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5.4-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5.4-mini")

    agency = Agency(
        agent1,
        communication_flows=[
            (agent1, agent2, [BrokenHandoff, CustomHandoff]),
        ],
    )

    runtime_state = agency.get_agent_runtime_state("Agent1")
    handoff_names = [handoff.tool_name for handoff in runtime_state.handoffs]
    assert handoff_names == ["custom_transfer_to_Agent2"]


def test_duplicate_communication_tool_class_is_rejected():
    """Test that multiple SendMessage tools for the same pair are rejected."""
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5.4-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5.4-mini")

    with pytest.raises(ValueError, match="Duplicate communication tool class detected"):
        Agency(
            agent1,
            communication_flows=[
                (agent1, agent2, SendMessage),
                (agent1, agent2, SendMessage),
            ],
        )

    with pytest.raises(ValueError, match="Each SendMessage tool for a pair can only be defined once"):
        Agency(
            agent1,
            communication_flows=[
                (agent1, agent2, CustomSendMessage),
                (agent1, agent2, OtherCustomSendMessage),
            ],
        )


def test_unsupported_communication_tool_class_is_rejected():
    """Test that communication flows only accept supported tool families."""
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5.4-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5.4-mini")

    with pytest.raises(TypeError, match="Expected a SendMessage or Handoff subclass"):
        Agency(
            agent1,
            communication_flows=[
                (agent1, agent2, [UnsupportedCommunicationTool, CustomSendMessage]),
            ],
        )


def test_empty_communication_tool_class_list_is_rejected():
    """Test that an explicit empty tool class list is not treated as a default flow."""
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5.4-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5.4-mini")

    with pytest.raises(ValueError, match="tool class list cannot be empty"):
        Agency(agent1, communication_flows=[(agent1, agent2, [])])


def test_duplicate_flow_detection_with_chains():
    """Test that duplicate flows are detected with AgentFlow chains."""
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5.4-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5.4-mini")
    agent3 = Agent(name="Agent3", instructions="Test agent 3", model="gpt-5.4-mini")

    with pytest.raises(ValueError, match="Duplicate communication tool class detected"):
        Agency(
            agent1,
            communication_flows=[
                (agent1 > agent2 > agent3, CustomSendMessage),  # Creates agent1->agent2
                (agent1, agent2),  # Duplicate agent1->agent2
            ],
        )


def test_agent_flow_with_handoff_tool():
    """Test that Handoff works with AgentFlow."""
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5.4-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5.4-mini")
    agent3 = Agent(name="Agent3", instructions="Test agent 3", model="gpt-5.4-mini")

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
    agent1 = Agent(name="Agent1", instructions="Test agent 1", model="gpt-5.4-mini")
    agent2 = Agent(name="Agent2", instructions="Test agent 2", model="gpt-5.4-mini")

    with pytest.deprecated_call(match=r"SendMessageHandoff is deprecated; use Handoff instead\."):
        Agency(
            agent1,
            communication_flows=[
                (agent1 > agent2, SendMessageHandoff),
            ],
        )

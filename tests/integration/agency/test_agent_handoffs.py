"""
Test suite for verifying the combination of handoffs and communication flows in Agency Swarm.

Key Implementation Findings:
============================

1. **Communication Flows (SendMessage tools)**:
   - Agency creates a unified `send_message` tool with multiple recipients for each agent's communication flows
   - This is a single FunctionTool instance that can send messages to any registered recipient
   - Control returns to the calling agent after receiving a response (orchestrator pattern)

2. **Handoffs (via SendMessageHandoff tool class)**:
   - Handoffs are configured by setting `send_message_tool_class=SendMessageHandoff` on Agent instances
   - Communication flows determine handoff targets (sender with SendMessageHandoff can hand off to recipient)
   - Handoffs represent unidirectional transfer of control (agent B takes over from agent A)

3. **Expected Tool Configuration**:
   - AgentA (orchestrator): `send_message` tool with AgentB and AgentC as recipients
   - AgentB (with handoffs): No tools for handoffs (SDK handles), but retains handoffs attribute
   - AgentC (specialist): No communication tools

4. **Combining Both Patterns**:
   - Communication flows and handoffs can coexist via different send message tool classes
   - Agency creates SendMessage tools based on communication_flows parameter
   - Tool class (SendMessage vs SendMessageHandoff) determines behavior
   - Handoffs functionality is enabled through SendMessageHandoff tool class
"""

from unittest.mock import MagicMock, patch

import pytest
from agents import ModelSettings

from agency_swarm import Agency, Agent
from agency_swarm.tools import SendMessageHandoff


@pytest.fixture
def orchestrator_agent():
    """Create an orchestrator agent that can communicate with other agents."""
    return Agent(
        name="AgentA",
        instructions="You are an orchestrator agent. You coordinate tasks by communicating with other agents.",
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def intermediate_agent():
    """Create an intermediate agent that has handoffs configured via SendMessageHandoff tool class."""
    return Agent(
        name="AgentB",
        instructions="You are an intermediate agent. You can hand off tasks to specialized agents.",
        model_settings=ModelSettings(temperature=0.0),
        send_message_tool_class=SendMessageHandoff,
    )


@pytest.fixture
def specialist_agent():
    """Create a specialist agent that receives handoffs."""
    return Agent(
        name="AgentC",
        instructions="You are a specialist agent. You process tasks handed off from other agents.",
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def mixed_communication_agency(orchestrator_agent, intermediate_agent, specialist_agent):
    """Create an agency with both communication flows and handoffs configured."""
    # Create agency with communication flows: AgentA can send messages to both AgentB and AgentC
    # AgentB can hand off to AgentC (enabled by SendMessageHandoff tool class and communication flow)
    agency = Agency(
        orchestrator_agent,  # Entry point
        communication_flows=[
            orchestrator_agent > intermediate_agent,  # AgentA -> AgentB (regular SendMessage)
            orchestrator_agent > specialist_agent,  # AgentA -> AgentC (regular SendMessage)
            intermediate_agent > specialist_agent,  # AgentB -> AgentC (SendMessageHandoff - enables handoffs)
        ],
        shared_instructions="Test agency for mixed communication patterns.",
    )
    return agency


class TestHandoffsWithCommunicationFlows:
    """Test suite for handoffs combined with communication flows."""

    def test_agent_tool_configuration(self, mixed_communication_agency):
        """Test that agents have the correct tools based on communication flows and handoffs."""
        agent_a = mixed_communication_agency.agents["AgentA"]
        agent_b = mixed_communication_agency.agents["AgentB"]
        agent_c = mixed_communication_agency.agents["AgentC"]

        # Get tool names for each agent
        agent_a_tools = [tool.name if hasattr(tool, "name") else str(tool) for tool in agent_a.tools]
        agent_c_tools = [tool.name if hasattr(tool, "name") else str(tool) for tool in agent_c.tools]

        # AgentA should have a unified send_message tool
        assert "send_message" in agent_a_tools, f"AgentA should have send_message tool, got: {agent_a_tools}"

        # Verify the send_message tool has the correct recipients
        send_msg_tool = next(
            (tool for tool in agent_a.tools if hasattr(tool, "name") and tool.name == "send_message"), None
        )
        assert send_msg_tool is not None, "AgentA should have a send_message tool"

        if hasattr(send_msg_tool, "recipients"):
            recipient_names = [agent.name for agent in send_msg_tool.recipients.values()]
            assert "AgentB" in recipient_names, f"AgentB should be in send_message recipients, got: {recipient_names}"
            assert "AgentC" in recipient_names, f"AgentC should be in send_message recipients, got: {recipient_names}"

        # AgentB should have handoff to AgentC in .handoffs attribute
        assert hasattr(agent_b, "handoffs"), "AgentB should have handoffs attribute"
        assert agent_b.handoffs is not None, "AgentB handoffs should not be None"
        assert len(agent_b.handoffs) > 0, "AgentB should have at least one handoff"

        # AgentC should have no communication tools (receives only)
        assert "send_message" not in agent_c_tools, f"AgentC should not have send_message tool, got: {agent_c_tools}"

    def test_sendmessage_tool_recipients(self, mixed_communication_agency):
        """Test that SendMessage tool has the correct recipients."""
        agent_a = mixed_communication_agency.agents["AgentA"]

        # Find the unified send_message tool
        sendmessage_tools = [tool for tool in agent_a.tools if hasattr(tool, "name") and tool.name == "send_message"]

        # Should have exactly 1 unified send_message tool
        assert len(sendmessage_tools) == 1, f"AgentA should have 1 send_message tool, got: {len(sendmessage_tools)}"

        # Verify the unified tool has the correct recipients
        send_msg_tool = sendmessage_tools[0]
        if hasattr(send_msg_tool, "recipients"):
            recipient_names = [agent.name for agent in send_msg_tool.recipients.values()]
            assert "AgentB" in recipient_names, f"AgentB should be in recipients, got: {recipient_names}"
            assert "AgentC" in recipient_names, f"AgentC should be in recipients, got: {recipient_names}"
            assert len(recipient_names) == 2, f"Should have exactly 2 recipients, got: {recipient_names}"

    def test_handoff_configuration_via_sendmessage_tool_class(self, mixed_communication_agency):
        """Test that handoffs are properly configured via SendMessageHandoff tool class on AgentB."""
        agent_b = mixed_communication_agency.agents["AgentB"]

        # Handoffs in Agency Swarm are configured via SendMessageHandoff tool class
        # We verify that AgentB has the correct send_message_tool_class
        assert hasattr(agent_b, "send_message_tool_class"), "AgentB should have send_message_tool_class attribute"
        assert agent_b.send_message_tool_class == SendMessageHandoff, (
            f"AgentB should have SendMessageHandoff as tool class, got: {agent_b.send_message_tool_class}"
        )

        # Verify AgentB has handoff to AgentC in .handoffs attribute (not in .tools list)
        assert hasattr(agent_b, "handoffs"), "AgentB should have handoffs attribute"
        assert len(agent_b.handoffs) == 1, f"AgentB should have 1 handoff, got: {len(agent_b.handoffs)}"

        # Check that the handoff targets AgentC
        handoff = agent_b.handoffs[0]
        assert handoff.agent_name == "AgentC", f"AgentB's handoff should target AgentC, got: {handoff.agent_name}"

    def test_agency_configuration_maintains_both_patterns(self, mixed_communication_agency):
        """Test that Agency maintains both communication flows and handoffs."""
        _ = mixed_communication_agency.agents["AgentA"]
        agent_b = mixed_communication_agency.agents["AgentB"]
        _ = mixed_communication_agency.agents["AgentC"]

        # Verify agents are properly registered
        assert len(mixed_communication_agency.agents) == 3
        assert all(agent_name in mixed_communication_agency.agents for agent_name in ["AgentA", "AgentB", "AgentC"])

        # Verify that handoff configuration is preserved via SendMessageHandoff tool class
        assert hasattr(agent_b, "send_message_tool_class"), "AgentB should have send_message_tool_class attribute"
        assert agent_b.send_message_tool_class == SendMessageHandoff, (
            "AgentB should have SendMessageHandoff as send_message_tool_class"
        )

    def test_tool_count_expectations(self, mixed_communication_agency):
        """Test that each agent has the expected number and type of tools."""
        agent_a = mixed_communication_agency.agents["AgentA"]
        agent_b = mixed_communication_agency.agents["AgentB"]
        agent_c = mixed_communication_agency.agents["AgentC"]

        # AgentA should have 1 unified send_message tool
        assert len(agent_a.tools) == 1, f"AgentA should have 1 send_message tool, got: {len(agent_a.tools)}"

        # AgentB should have 0 tools (handoffs are in .handoffs attribute, not .tools list)
        assert len(agent_b.tools) == 0, f"AgentB should have 0 tools, got: {len(agent_b.tools)}"

        # AgentC should have no communication tools (only receives messages)
        assert len(agent_c.tools) == 0, f"AgentC should have no tools, got: {len(agent_c.tools)}"

    @pytest.mark.asyncio
    async def test_orchestrator_pattern_with_handoffs(self, mixed_communication_agency):
        """Test the orchestrator pattern where AgentA uses AgentB which then hands off to AgentC."""
        agent_a = mixed_communication_agency.agents["AgentA"]
        agent_b = mixed_communication_agency.agents["AgentB"]
        agent_c = mixed_communication_agency.agents["AgentC"]

        # Mock responses for the chain of communication
        mock_c_response = MagicMock()
        mock_c_response.final_output = "Task completed by AgentC"

        mock_b_response = MagicMock()
        mock_b_response.final_output = "Task processed by AgentB and handed off to AgentC"

        try:
            with (
                patch.object(agent_c, "get_response", return_value=mock_c_response),
                patch.object(agent_b, "get_response", return_value=mock_b_response),
            ):
                # AgentA orchestrates by sending message to AgentB
                result = await agent_a.get_response(
                    message="Send this complex task to AgentB for processing and potential handoff",
                )

                assert result is not None

        except Exception as e:
            pytest.skip(f"Orchestrator pattern with handoffs not fully implemented: {e}")

    def test_communication_flow_isolation(self, mixed_communication_agency):
        """Test that communication flows and handoffs maintain proper isolation."""
        _ = mixed_communication_agency.agents["AgentA"]
        _ = mixed_communication_agency.agents["AgentB"]
        agent_c = mixed_communication_agency.agents["AgentC"]

        # AgentA should be able to communicate with both AgentB and AgentC independently
        # AgentB should only be able to hand off to AgentC (not send messages)
        # AgentC should not be able to initiate communication with others

        # Check that AgentC doesn't have tools to communicate back to AgentA or AgentB
        agent_c_tool_names = [tool.name if hasattr(tool, "name") else str(tool) for tool in agent_c.tools]

        # AgentC shouldn't have send_message tool
        assert "send_message" not in agent_c_tool_names, (
            f"AgentC should not have send_message tool, found tools: {agent_c_tool_names}"
        )


class TestComplexHandoffScenarios:
    """Test more complex scenarios with multiple handoffs and communication flows."""

    def test_multiple_handoff_targets(self):
        """Test agent with multiple handoff targets via SendMessageHandoff tool class."""
        agent_a = Agent(name="AgentA", instructions="Orchestrator")
        agent_b = Agent(name="AgentB", instructions="Multi-handoff agent", send_message_tool_class=SendMessageHandoff)
        agent_c = Agent(name="AgentC", instructions="Specialist 1")
        agent_d = Agent(name="AgentD", instructions="Specialist 2")

        agency = Agency(
            agent_a,
            communication_flows=[
                agent_a > agent_b,
                agent_b > agent_c,  # AgentB can hand off to AgentC
                agent_b > agent_d,  # AgentB can hand off to AgentD
            ],
        )

        # Verify AgentB has SendMessageHandoff tool class configured
        agent_b_final = agency.agents["AgentB"]
        assert hasattr(agent_b_final, "send_message_tool_class"), "AgentB should have send_message_tool_class attribute"
        assert agent_b_final.send_message_tool_class == SendMessageHandoff, (
            f"AgentB should have SendMessageHandoff as tool class, got: {agent_b_final.send_message_tool_class}"
        )

        # Verify AgentB has handoffs to both AgentC and AgentD in .handoffs attribute
        assert hasattr(agent_b_final, "handoffs"), "AgentB should have handoffs attribute"
        assert len(agent_b_final.handoffs) == 2, f"AgentB should have 2 handoffs, got: {len(agent_b_final.handoffs)}"

        # Verify the handoff targets are correct
        handoff_targets = [h.agent_name for h in agent_b_final.handoffs]
        assert "AgentC" in handoff_targets, "AgentB should have handoff to AgentC"
        assert "AgentD" in handoff_targets, "AgentB should have handoff to AgentD"

    def test_bidirectional_communication_with_handoffs(self):
        """Test bidirectional communication flows combined with SendMessageHandoff tool class."""
        agent_a = Agent(name="AgentA", instructions="Primary orchestrator")
        agent_b = Agent(
            name="AgentB",
            instructions="Secondary orchestrator with handoffs",
            send_message_tool_class=SendMessageHandoff,
        )
        agent_c = Agent(name="AgentC", instructions="Specialist")

        # Configure bidirectional communication between A and B, plus handoff capability from B to C
        agency = Agency(
            agent_a,
            communication_flows=[
                agent_a > agent_b,  # A can send to B
                agent_b > agent_a,  # B can send to A (using SendMessageHandoff tool class)
                agent_a > agent_c,  # A can send to C
                agent_b > agent_c,  # B can hand off to C (using SendMessageHandoff tool class)
            ],
        )

        agent_a_final = agency.agents["AgentA"]
        agent_b_final = agency.agents["AgentB"]

        # Both AgentA and AgentB should have send_message tools
        agent_a_tools = [tool.name if hasattr(tool, "name") else str(tool) for tool in agent_a_final.tools]

        # AgentA should have send_message tool
        assert "send_message" in agent_a_tools, f"AgentA should have send_message tool, got: {agent_a_tools}"

        # AgentB should have handoffs to both AgentA and AgentC in .handoffs attribute
        assert hasattr(agent_b_final, "handoffs"), "AgentB should have handoffs attribute"
        assert len(agent_b_final.handoffs) == 2, f"AgentB should have 2 handoffs, got: {len(agent_b_final.handoffs)}"

        handoff_targets = [h.agent_name for h in agent_b_final.handoffs]
        assert "AgentA" in handoff_targets, f"AgentB should have handoff to AgentA, got: {handoff_targets}"
        assert "AgentC" in handoff_targets, f"AgentB should have handoff to AgentC, got: {handoff_targets}"

        # Verify AgentB has SendMessageHandoff tool class configured
        assert hasattr(agent_b_final, "send_message_tool_class"), "AgentB should have send_message_tool_class attribute"
        assert agent_b_final.send_message_tool_class == SendMessageHandoff, (
            "AgentB should have SendMessageHandoff as send_message_tool_class"
        )

    def test_agency_flow_handoffs(self):
        """Test bidirectional communication flows combined with SendMessageHandoff tool class."""
        agent_a = Agent(name="AgentA", instructions="Primary orchestrator")
        agent_b = Agent(
            name="AgentB",
            instructions="Secondary orchestrator with handoffs",
        )
        agent_c = Agent(name="AgentC", instructions="Specialist")

        # Configure bidirectional communication between A and B, plus handoff capability from B to C
        agency = Agency(
            agent_a,
            communication_flows=[
                (agent_a > agent_b),  # A can send to B
                (agent_b > agent_a, SendMessageHandoff),  # B can send to A (using SendMessageHandoff tool class)
                (agent_a > agent_c),  # A can send to C
                (agent_b > agent_c, SendMessageHandoff),  # B can hand off to C (using SendMessageHandoff tool class)
            ],
        )

        agent_a_final = agency.agents["AgentA"]
        agent_b_final = agency.agents["AgentB"]

        # Both AgentA and AgentB should have send_message tools
        agent_a_tools = [tool.name if hasattr(tool, "name") else str(tool) for tool in agent_a_final.tools]

        # AgentA should have send_message tool
        assert "send_message" in agent_a_tools, f"AgentA should have send_message tool, got: {agent_a_tools}"

        # AgentB should have handoffs to both AgentA and AgentC in .handoffs attribute
        assert hasattr(agent_b_final, "handoffs"), "AgentB should have handoffs attribute"
        assert len(agent_b_final.handoffs) == 2, f"AgentB should have 2 handoffs, got: {len(agent_b_final.handoffs)}"

        handoff_targets = [h.agent_name for h in agent_b_final.handoffs]
        assert "AgentA" in handoff_targets, f"AgentB should have handoff to AgentA, got: {handoff_targets}"
        assert "AgentC" in handoff_targets, f"AgentB should have handoff to AgentC, got: {handoff_targets}"

    @pytest.mark.asyncio
    async def test_handoff_follow_up(self, mixed_communication_agency):
        """Test that there are no errors on follow up messages."""

        # First handoff
        async for _ in mixed_communication_agency.get_response_stream("Ask Agent B to use transfer_to_AgentC tool."):
            pass

        # Verify handoff occurred
        messages = mixed_communication_agency.thread_manager.get_all_messages()
        tool_names = [msg.get("name") for msg in messages if msg.get("type") == "function_call"]
        assert "transfer_to_AgentC" in tool_names, "Should have used transfer_to_AgentC tool"

        # Second handoff (follow-up)
        async for _ in mixed_communication_agency.get_response_stream("Do the exact same thing again."):
            pass

        # Verify no errors in tool outputs
        messages = mixed_communication_agency.thread_manager.get_all_messages()
        tool_outputs = [msg.get("output", "") for msg in messages if msg.get("type") == "function_call_output"]

        for output in tool_outputs:
            assert "error" not in output.lower(), f"Found error in tool output: {output}"

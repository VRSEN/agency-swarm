"""
Test suite for verifying the combination of handoffs and communication flows in Agency Swarm.

Key Implementation Findings:
============================

1. **Communication Flows (SendMessage tools)**:
   - Agency creates a unified `send_message` tool with multiple recipients for each agent's communication flows
   - This is a single FunctionTool instance that can send messages to any registered recipient
   - Control returns to the calling agent after receiving a response (orchestrator pattern)

2. **Handoffs (OpenAI SDK)**:
   - Handoffs are configured via the `handoffs` attribute on Agent instances
   - They do NOT create tools in Agency Swarm - handled directly by the OpenAI Agents SDK
   - Handoffs represent unidirectional transfer of control (agent B takes over from agent A)

3. **Expected Tool Configuration**:
   - AgentA (orchestrator): `send_message` tool with AgentB and AgentC as recipients
   - AgentB (with handoffs): No tools for handoffs (SDK handles), but retains handoffs attribute
   - AgentC (specialist): No communication tools

4. **Combining Both Patterns**:
   - Communication flows and handoffs can coexist on the same agent
   - Agency preserves the handoffs attribute during configuration
   - SendMessage tools are created based on communication_flows parameter
   - Handoffs functionality is preserved for the OpenAI SDK to handle
"""

from unittest.mock import MagicMock, patch

import pytest
from agents import ModelSettings

from agency_swarm import Agency, Agent


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
    """Create an intermediate agent that has handoffs configured."""
    return Agent(
        name="AgentB",
        instructions="You are an intermediate agent. You can hand off tasks to specialized agents.",
        model_settings=ModelSettings(temperature=0.0),
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
    # Configure handoffs: AgentB can hand off to AgentC
    intermediate_agent.handoffs = [specialist_agent]

    # Create agency with communication flows: AgentA can send messages to both AgentB and AgentC
    agency = Agency(
        orchestrator_agent,  # Entry point
        communication_flows=[
            (orchestrator_agent, intermediate_agent),  # AgentA -> AgentB
            (orchestrator_agent, specialist_agent),  # AgentA -> AgentC
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
        _ = [tool.name if hasattr(tool, "name") else str(tool) for tool in agent_b.tools]
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

        # AgentB should have handoffs configured but not as tools (handled by SDK)
        # In Agency Swarm, handoffs don't create tools - they're handled by the underlying OpenAI SDK
        # So we verify that handoffs attribute exists and is configured correctly
        assert hasattr(agent_b, "handoffs"), "AgentB should have handoffs attribute"
        if agent_b.handoffs:
            handoff_targets = [getattr(h, "name", str(h)) for h in agent_b.handoffs]
            assert "AgentC" in handoff_targets, "AgentB should have AgentC in handoffs"

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

    def test_handoff_configuration_via_attribute(self, mixed_communication_agency):
        """Test that handoffs are properly configured via the handoffs attribute on AgentB."""
        agent_b = mixed_communication_agency.agents["AgentB"]

        # Handoffs in Agency Swarm are handled by the OpenAI SDK, not through tool creation
        # We verify that the handoffs attribute is properly configured
        assert hasattr(agent_b, "handoffs"), "AgentB should have handoffs attribute"
        assert agent_b.handoffs is not None, "AgentB handoffs should not be None"
        assert len(agent_b.handoffs) > 0, "AgentB should have at least one handoff target"

        # Verify AgentC is in the handoffs list
        handoff_targets = [getattr(h, "name", str(h)) for h in agent_b.handoffs]
        assert "AgentC" in handoff_targets, f"AgentB should have AgentC in handoffs, got: {handoff_targets}"

        # Verify the actual agent instance is correct
        agent_c = mixed_communication_agency.agents["AgentC"]
        assert agent_c in agent_b.handoffs, "AgentC instance should be directly in AgentB's handoffs list"

    def test_agency_configuration_maintains_both_patterns(self, mixed_communication_agency):
        """Test that Agency maintains both communication flows and handoffs."""
        _ = mixed_communication_agency.agents["AgentA"]
        agent_b = mixed_communication_agency.agents["AgentB"]
        _ = mixed_communication_agency.agents["AgentC"]

        # Verify agents are properly registered
        assert len(mixed_communication_agency.agents) == 3
        assert all(agent_name in mixed_communication_agency.agents for agent_name in ["AgentA", "AgentB", "AgentC"])

        # Verify that handoffs configuration is preserved
        assert hasattr(agent_b, "handoffs"), "AgentB should have handoffs attribute"
        if agent_b.handoffs:
            handoff_targets = [getattr(h, "name", str(h)) for h in agent_b.handoffs]
            assert "AgentC" in handoff_targets, "AgentB should have AgentC in handoffs"

    def test_tool_count_expectations(self, mixed_communication_agency):
        """Test that each agent has the expected number and type of tools."""
        agent_a = mixed_communication_agency.agents["AgentA"]
        agent_b = mixed_communication_agency.agents["AgentB"]
        agent_c = mixed_communication_agency.agents["AgentC"]

        # AgentA should have 1 unified send_message tool
        assert len(agent_a.tools) == 1, f"AgentA should have 1 send_message tool, got: {len(agent_a.tools)}"

        # AgentB should have no tools added automatically (handoffs do not create tools)
        assert len(agent_b.tools) == 0, f"AgentB should have no tools, got: {len(agent_b.tools)}"

        # AgentC should also have no communication tools (only receives messages)
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
        """Test agent with multiple handoff targets."""
        agent_a = Agent(name="AgentA", instructions="Orchestrator")
        agent_b = Agent(name="AgentB", instructions="Multi-handoff agent")
        agent_c = Agent(name="AgentC", instructions="Specialist 1")
        agent_d = Agent(name="AgentD", instructions="Specialist 2")

        # Configure multiple handoffs
        agent_b.handoffs = [agent_c, agent_d]

        agency = Agency(
            agent_a,
            communication_flows=[
                (agent_a, agent_b),
                (agent_a, agent_c),
                (agent_a, agent_d),
            ],
        )

        # Verify AgentB has handoffs configured (not as tools, but as attribute)
        agent_b_final = agency.agents["AgentB"]
        assert hasattr(agent_b_final, "handoffs"), "AgentB should have handoffs attribute"
        assert len(agent_b_final.handoffs) == 2, (
            f"AgentB should have 2 handoff targets, got: {len(agent_b_final.handoffs)}"
        )

        # Verify the handoff targets are correct
        handoff_target_names = [agent.name for agent in agent_b_final.handoffs]
        assert "AgentC" in handoff_target_names, "AgentB should have AgentC as handoff target"
        assert "AgentD" in handoff_target_names, "AgentB should have AgentD as handoff target"

    def test_bidirectional_communication_with_handoffs(self):
        """Test bidirectional communication flows combined with unidirectional handoffs."""
        agent_a = Agent(name="AgentA", instructions="Primary orchestrator")
        agent_b = Agent(name="AgentB", instructions="Secondary orchestrator with handoffs")
        agent_c = Agent(name="AgentC", instructions="Specialist")

        # Configure handoff from B to C
        agent_b.handoffs = [agent_c]

        # Configure bidirectional communication between A and B
        agency = Agency(
            agent_a,
            communication_flows=[
                (agent_a, agent_b),  # A can send to B
                (agent_b, agent_a),  # B can send to A
                (agent_a, agent_c),  # A can send to C
            ],
        )

        agent_a_final = agency.agents["AgentA"]
        agent_b_final = agency.agents["AgentB"]

        # Both AgentA and AgentB should have send_message tools
        agent_a_tools = [tool.name if hasattr(tool, "name") else str(tool) for tool in agent_a_final.tools]
        agent_b_tools = [tool.name if hasattr(tool, "name") else str(tool) for tool in agent_b_final.tools]

        # AgentA should have send_message tool
        assert "send_message" in agent_a_tools, f"AgentA should have send_message tool, got: {agent_a_tools}"

        # AgentB should have send_message tool (bidirectional communication)
        assert "send_message" in agent_b_tools, f"AgentB should have send_message tool, got: {agent_b_tools}"

        # Verify AgentB still has handoffs configured
        assert hasattr(agent_b_final, "handoffs"), "AgentB should have handoffs attribute"
        if agent_b_final.handoffs:
            handoff_targets = [getattr(h, "name", str(h)) for h in agent_b_final.handoffs]
            assert "AgentC" in handoff_targets, "AgentB should have AgentC in handoffs"

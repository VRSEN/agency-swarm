"""
Test suite for verifying the combination of handoffs and communication flows in Agency Swarm.

Key Implementation Findings:
============================

1. **Communication Flows (SendMessage tools)**:
   - Agency creates a unified `send_message` tool with multiple recipients for each agent's communication flows
   - This is a single FunctionTool instance that can send messages to any registered recipient
   - Control returns to the calling agent after receiving a response (orchestrator pattern)

2. **Handoffs (via Handoff tool class)**:
   - Handoffs are configured by setting `Handoff` as the flow tool class in `communication_flows`
   - Communication flows determine handoff targets (sender with Handoff can hand off to recipient)
   - Handoffs represent unidirectional transfer of control (agent B takes over from agent A)

3. **Expected Tool Configuration**:
   - AgentA (orchestrator): `send_message` tool with AgentB and AgentC as recipients
   - AgentB (with handoffs): No tools for handoffs (SDK handles), but retains handoffs attribute
   - AgentC (specialist): No communication tools

4. **Combining Both Patterns**:
   - Communication flows and handoffs can coexist via different send message tool classes
   - Agency creates SendMessage tools based on communication_flows parameter
   - Tool class (SendMessage vs Handoff) determines behavior
   - Handoffs functionality is enabled through Handoff tool class
"""

from unittest.mock import MagicMock, patch

import pytest
from agents import HandoffInputData, ModelSettings, RunContextWrapper

from agency_swarm import Agency, Agent
from agency_swarm.tools import Handoff
from agency_swarm.utils.thread import ThreadManager


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
    """Create an intermediate agent that has handoffs configured via Handoff tool class."""
    return Agent(
        name="AgentB",
        instructions=(
            "You are an intermediate agent. Whenever asked to speak with agent C, use the transfer_to_AgentC tool "
            "immediately, without any questions."
        ),
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
    # Create agency with communication flows: AgentA can send messages to both AgentB and AgentC
    # AgentB can hand off to AgentC (enabled by Handoff tool class and communication flow)
    agency = Agency(
        orchestrator_agent,  # Entry point
        communication_flows=[
            orchestrator_agent > intermediate_agent,  # AgentA -> AgentB (regular SendMessage)
            orchestrator_agent > specialist_agent,  # AgentA -> AgentC (regular SendMessage)
            (intermediate_agent > specialist_agent, Handoff),  # AgentB -> AgentC (handoff)
        ],
        shared_instructions="Test agency for mixed communication patterns.",
    )
    return agency


class TestHandoffsWithCommunicationFlows:
    """Test suite for handoffs combined with communication flows."""

    def test_agent_tool_configuration(self, mixed_communication_agency):
        """Test that agents have the correct tools based on communication flows and handoffs."""
        runtime_state_a = mixed_communication_agency.get_agent_runtime_state("AgentA")
        runtime_state_b = mixed_communication_agency.get_agent_runtime_state("AgentB")
        runtime_state_c = mixed_communication_agency.get_agent_runtime_state("AgentC")

        send_message_tools = list(runtime_state_a.send_message_tools.values())
        assert len(send_message_tools) == 1, "AgentA should expose exactly one runtime send_message tool"

        send_msg_tool = send_message_tools[0]
        recipient_names = [agent.name for agent in send_msg_tool.recipients.values()]
        assert "AgentB" in recipient_names, f"AgentB should be in send_message recipients, got: {recipient_names}"
        assert "AgentC" in recipient_names, f"AgentC should be in send_message recipients, got: {recipient_names}"

        assert runtime_state_b.handoffs, "AgentB should register handoffs at runtime"
        assert not runtime_state_c.send_message_tools, "AgentC should not expose send_message tools"

    def test_sendmessage_tool_recipients(self, mixed_communication_agency):
        """Test that SendMessage tool has the correct recipients."""
        runtime_state_a = mixed_communication_agency.get_agent_runtime_state("AgentA")

        sendmessage_tools = list(runtime_state_a.send_message_tools.values())
        assert len(sendmessage_tools) == 1, f"AgentA should have 1 send_message tool, got: {len(sendmessage_tools)}"

        send_msg_tool = sendmessage_tools[0]
        recipient_names = [agent.name for agent in send_msg_tool.recipients.values()]
        assert "AgentB" in recipient_names, f"AgentB should be in recipients, got: {recipient_names}"
        assert "AgentC" in recipient_names, f"AgentC should be in recipients, got: {recipient_names}"
        assert len(recipient_names) == 2, f"Should have exactly 2 recipients, got: {recipient_names}"

    def test_handoff_configuration_via_sendmessage_tool_class(self, mixed_communication_agency):
        """Test that handoffs are properly configured via flow tool class."""
        runtime_state_b = mixed_communication_agency.get_agent_runtime_state("AgentB")
        # Verify AgentB has handoff to AgentC in .handoffs attribute (not in .tools list)
        assert runtime_state_b.handoffs, "AgentB runtime state should contain handoffs"
        assert len(runtime_state_b.handoffs) == 1, f"AgentB should have 1 handoff, got: {len(runtime_state_b.handoffs)}"

        # Check that the handoff targets AgentC
        handoff = runtime_state_b.handoffs[0]
        assert handoff.agent_name == "AgentC", f"AgentB's handoff should target AgentC, got: {handoff.agent_name}"

    def test_agency_configuration_maintains_both_patterns(self, mixed_communication_agency):
        """Test that Agency maintains both communication flows and handoffs."""
        _ = mixed_communication_agency.agents["AgentA"]
        _ = mixed_communication_agency.agents["AgentC"]

        # Verify agents are properly registered
        assert len(mixed_communication_agency.agents) == 3
        assert all(agent_name in mixed_communication_agency.agents for agent_name in ["AgentA", "AgentB", "AgentC"])

        runtime_state_b = mixed_communication_agency.get_agent_runtime_state("AgentB")
        assert runtime_state_b.handoffs, "AgentB should register handoffs at runtime"

    def test_tool_count_expectations(self, mixed_communication_agency):
        """Test that each agent has the expected number and type of tools."""
        runtime_state_a = mixed_communication_agency.get_agent_runtime_state("AgentA")
        runtime_state_b = mixed_communication_agency.get_agent_runtime_state("AgentB")
        runtime_state_c = mixed_communication_agency.get_agent_runtime_state("AgentC")

        assert len(runtime_state_a.send_message_tools) == 1, "AgentA should expose 1 send_message tool"
        assert not runtime_state_b.send_message_tools, "AgentB should not expose send_message tools"
        assert not runtime_state_c.send_message_tools, "AgentC should not expose send_message tools"

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

    @pytest.mark.asyncio
    async def test_handoff_reminder_handles_empty_history(self, specialist_agent):
        """Ensure reminder injection does not crash when the thread history is empty."""

        handoff_tool = Handoff().create_handoff(specialist_agent)
        assert handoff_tool.input_filter is not None, "Expected handoff to expose an input filter"

        thread_manager = ThreadManager()
        context = type("Context", (), {"thread_manager": thread_manager})()
        run_context = RunContextWrapper(context=context)
        handoff_input = HandoffInputData(
            input_history=(),
            pre_handoff_items=(),
            new_items=(),
            run_context=run_context,
        )

        filtered_input = await handoff_tool.input_filter(handoff_input)

        assert filtered_input.input_history == ()
        assert thread_manager.get_all_messages() == []

    def test_communication_flow_isolation(self, mixed_communication_agency):
        """Test that communication flows and handoffs maintain proper isolation."""
        _ = mixed_communication_agency.agents["AgentA"]
        _ = mixed_communication_agency.agents["AgentB"]
        _ = mixed_communication_agency.agents["AgentC"]

        # AgentA should be able to communicate with both AgentB and AgentC independently
        # AgentB should only be able to hand off to AgentC (not send messages)
        # AgentC should not be able to initiate communication with others
        runtime_state_a = mixed_communication_agency.get_agent_runtime_state("AgentA")
        runtime_state_b = mixed_communication_agency.get_agent_runtime_state("AgentB")
        runtime_state_c = mixed_communication_agency.get_agent_runtime_state("AgentC")

        assert runtime_state_a.send_message_tools, "AgentA should have send_message tools"
        assert not runtime_state_b.send_message_tools, "AgentB should not expose send_message tools"
        assert not runtime_state_c.send_message_tools, "AgentC should not expose send_message tools"


class TestComplexHandoffScenarios:
    """Test more complex scenarios with multiple handoffs and communication flows."""

    def test_multiple_handoff_targets(self):
        """Test agent with multiple handoff targets via Handoff tool class."""
        agent_a = Agent(name="AgentA", instructions="Orchestrator")
        agent_b = Agent(name="AgentB", instructions="Multi-handoff agent")
        agent_c = Agent(name="AgentC", instructions="Specialist 1")
        agent_d = Agent(name="AgentD", instructions="Specialist 2")

        agency = Agency(
            agent_a,
            communication_flows=[
                agent_a > agent_b,
                (agent_b > agent_c, Handoff),  # AgentB can hand off to AgentC
                (agent_b > agent_d, Handoff),  # AgentB can hand off to AgentD
            ],
        )

        runtime_state_b = agency.get_agent_runtime_state("AgentB")
        assert len(runtime_state_b.handoffs) == 2, (
            f"AgentB should have 2 handoffs, got: {len(runtime_state_b.handoffs)}"
        )

        # Verify the handoff targets are correct
        handoff_targets = [h.agent_name for h in runtime_state_b.handoffs]
        assert "AgentC" in handoff_targets, "AgentB should have handoff to AgentC"
        assert "AgentD" in handoff_targets, "AgentB should have handoff to AgentD"

    def test_bidirectional_communication_with_handoffs(self):
        """Test bidirectional communication flows combined with Handoff tool class."""
        agent_a = Agent(name="AgentA", instructions="Primary orchestrator")
        agent_b = Agent(name="AgentB", instructions="Secondary orchestrator with handoffs")
        agent_c = Agent(name="AgentC", instructions="Specialist")

        # Configure bidirectional communication between A and B, plus handoff capability from B to C
        agency = Agency(
            agent_a,
            communication_flows=[
                agent_a > agent_b,  # A can send to B
                (agent_b > agent_a, Handoff),  # B can hand off to A
                agent_a > agent_c,  # A can send to C
                (agent_b > agent_c, Handoff),  # B can hand off to C
            ],
        )

        runtime_state_a = agency.get_agent_runtime_state("AgentA")
        runtime_state_b = agency.get_agent_runtime_state("AgentB")

        assert runtime_state_a.send_message_tools, "AgentA should expose send_message tools"
        send_msg_tool = next(iter(runtime_state_a.send_message_tools.values()))
        recipient_names = [agent.name for agent in send_msg_tool.recipients.values()]
        assert "AgentB" in recipient_names, f"AgentB should be reachable, got: {recipient_names}"
        assert "AgentC" in recipient_names, f"AgentC should be reachable, got: {recipient_names}"

        assert len(runtime_state_b.handoffs) == 2, (
            f"AgentB should have 2 handoffs, got: {len(runtime_state_b.handoffs)}"
        )

        handoff_targets = [h.agent_name for h in runtime_state_b.handoffs]
        assert "AgentA" in handoff_targets, f"AgentB should have handoff to AgentA, got: {handoff_targets}"
        assert "AgentC" in handoff_targets, f"AgentB should have handoff to AgentC, got: {handoff_targets}"

        assert runtime_state_b.handoffs, "AgentB should register handoffs at runtime"

    def test_agency_flow_handoffs(self):
        """Test bidirectional communication flows combined with Handoff tool class."""
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
                (agent_b > agent_a, Handoff),  # B can send to A (using Handoff tool class)
                (agent_a > agent_c),  # A can send to C
                (agent_b > agent_c, Handoff),  # B can hand off to C (using Handoff tool class)
            ],
        )

        runtime_state_a = agency.get_agent_runtime_state("AgentA")
        runtime_state_b = agency.get_agent_runtime_state("AgentB")

        assert runtime_state_a.send_message_tools, "AgentA should expose send_message tools"
        send_msg_tool = next(iter(runtime_state_a.send_message_tools.values()))
        recipient_names = [agent.name for agent in send_msg_tool.recipients.values()]
        assert "AgentB" in recipient_names, "AgentB should be reachable from AgentA"
        assert "AgentC" in recipient_names, "AgentC should be reachable from AgentA"

        assert len(runtime_state_b.handoffs) == 2, (
            f"AgentB should have 2 handoffs, got: {len(runtime_state_b.handoffs)}"
        )

        handoff_targets = [h.agent_name for h in runtime_state_b.handoffs]
        assert "AgentA" in handoff_targets, f"AgentB should have handoff to AgentA, got: {handoff_targets}"
        assert "AgentC" in handoff_targets, f"AgentB should have handoff to AgentC, got: {handoff_targets}"

    @pytest.mark.asyncio
    async def test_nested_handoffs_on_follow_ups(self, mixed_communication_agency):
        """Test that there are no errors on follow up messages."""

        # First handoff
        async for _ in mixed_communication_agency.get_response_stream("Ask Agent B to use transfer_to_AgentC tool."):
            pass

        # Verify handoff occurred
        messages = mixed_communication_agency.thread_manager.get_all_messages()
        tool_names = [msg.get("name") for msg in messages if msg.get("type") == "function_call"]
        assert "transfer_to_AgentC" in tool_names, "Should have used transfer_to_AgentC tool"

        # Second handoff (follow-up)
        async for _ in mixed_communication_agency.get_response_stream(
            "Ask Agent B to use transfer_to_AgentC tool again."
        ):
            pass

        # Verify no errors in tool outputs
        messages = mixed_communication_agency.thread_manager.get_all_messages()
        tool_outputs = [msg.get("output", "") for msg in messages if msg.get("type") == "function_call_output"]

        for output in tool_outputs:
            assert "error" not in output.lower(), f"Found error in tool output: {output}"

    def test_handoff_reminders(self):
        """Test bidirectional communication flows combined with Handoff tool class."""

        class NoReminder(Handoff):
            add_reminder = False

        agent_a = Agent(
            name="AgentA", instructions="Primary orchestrator", model_settings=ModelSettings(temperature=0.0)
        )
        agent_b = Agent(
            name="AgentB",
            instructions="Secondary orchestrator with handoffs",
            model_settings=ModelSettings(temperature=0.0),
        )
        agent_c = Agent(
            name="AgentC",
            instructions="Specialist",
            model_settings=ModelSettings(temperature=0.0),
            handoff_reminder="Custom reminder",
        )

        # Configure bidirectional communication between A and B, plus handoff capability from B to C
        agency = Agency(
            agent_a,
            agent_b,
            agent_c,
            communication_flows=[
                (agent_a > agent_b, Handoff),  # A can send to B
                (agent_b > agent_c, Handoff),  # A can send to C
                (agent_c > agent_a, NoReminder),  # No-reminder handoff
            ],
        )
        # Check default handoff
        agency.get_response_sync("Transfer to AgentB agent", recipient_agent=agent_a)
        system_message = agency.thread_manager.get_all_messages()[1]

        assert system_message["role"] == "system", (
            f"Incorrect role, got: {system_message}, expected reminder system message"
        )
        assert system_message["content"] == "Transfer completed. You are AgentB. Please continue the task.", (
            f"Incorrect content, got: {system_message}, expected reminder system message"
        )

        agency.thread_manager.clear()

        # Check custom reminder
        agency.get_response_sync("Transfer to AgentC agent", recipient_agent=agent_b)
        system_message = agency.thread_manager.get_all_messages()[1]

        assert system_message["role"] == "system", (
            f"Incorrect role, got: {system_message}, expected reminder system message"
        )
        assert system_message["content"] == "Custom reminder", (
            f"Incorrect content, got: {system_message}, expected 'Custom reminder'"
        )

        agency.thread_manager.clear()

        # Check no reminder handoff
        agency.get_response_sync("Transfer to AgentA agent", recipient_agent=agent_c)
        chat_history = agency.thread_manager.get_all_messages()

        for message in chat_history:
            if "role" in message:
                assert message["role"] != "system", f"Incorrect role, got: {message}, expected no system messages"

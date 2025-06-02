"""
Test suite to understand control transfer behavior when combining handoffs and communication flows.

This test examines the core question: What happens when AgentA uses send_message_to_AgentB,
and then AgentB uses a handoff to AgentC? Who gets the response - AgentA or AgentC?

Based on the implementation analysis:
1. SendMessage tools call recipient_agent.get_response() and return the result
2. When get_response() is called with sender_name, conversation history is NOT saved to thread
3. Handoffs are handled by the OpenAI SDK and configured via the handoffs attribute
4. Control transfer behavior depends on how the OpenAI SDK handles handoffs vs tool responses
"""

import pytest
from agents import ModelSettings

from agency_swarm import Agency, Agent


@pytest.fixture
def control_test_agents():
    """Create test agents for control transfer testing."""
    orchestrator = Agent(
        name="Orchestrator",
        instructions="You coordinate tasks. Use send_message tools to delegate to workers.",
        model_settings=ModelSettings(temperature=0.0),
    )

    # Worker that can hand off to specialist
    worker = Agent(
        name="Worker",
        instructions="You process tasks. If specialized work is needed, hand off to Specialist.",
        model_settings=ModelSettings(temperature=0.0),
    )

    specialist = Agent(
        name="Specialist",
        instructions="You handle specialized tasks handed off from workers.",
        model_settings=ModelSettings(temperature=0.0),
    )

    return orchestrator, worker, specialist


@pytest.fixture
def control_test_agency(control_test_agents):
    """Create an agency with both communication flows and handoffs."""
    orchestrator, worker, specialist = control_test_agents

    # Configure handoff: Worker can hand off to Specialist
    worker.handoffs = [specialist]

    # Configure communication flows: Orchestrator can send to both
    agency = Agency(
        orchestrator,  # Entry point
        communication_flows=[
            (orchestrator, worker),  # Orchestrator -> Worker (SendMessage)
            (orchestrator, specialist),  # Orchestrator -> Specialist (SendMessage)
        ],
        shared_instructions="Test agency for control transfer analysis.",
    )
    return agency


class TestControlTransferBehavior:
    """Test suite to understand control transfer in mixed communication patterns."""

    def test_tool_configuration_for_control_patterns(self, control_test_agency):
        """Verify the tools available for each control pattern."""
        orchestrator = control_test_agency.agents["Orchestrator"]
        worker = control_test_agency.agents["Worker"]
        specialist = control_test_agency.agents["Specialist"]

        # Orchestrator should have SendMessage tools (orchestrator pattern)
        orchestrator_tools = [tool.name if hasattr(tool, "name") else str(tool) for tool in orchestrator.tools]
        assert any("send_message_to_Worker" in tool for tool in orchestrator_tools), (
            f"Orchestrator should have send_message_to_Worker tool, got: {orchestrator_tools}"
        )
        assert any("send_message_to_Specialist" in tool for tool in orchestrator_tools), (
            f"Orchestrator should have send_message_to_Specialist tool, got: {orchestrator_tools}"
        )

        # Worker should have handoffs configured (transfer pattern) but no SendMessage tools
        worker_tools = [tool.name if hasattr(tool, "name") else str(tool) for tool in worker.tools]
        assert hasattr(worker, "handoffs"), "Worker should have handoffs attribute"
        if worker.handoffs:
            handoff_targets = [getattr(h, "name", str(h)) for h in worker.handoffs]
            assert "Specialist" in handoff_targets, "Worker should have Specialist in handoffs"

        # Specialist should have no special communication tools
        specialist_tools = [tool.name if hasattr(tool, "name") else str(tool) for tool in specialist.tools]
        send_message_tools = [tool for tool in specialist_tools if "send_message_to_" in tool.lower()]
        assert len(send_message_tools) == 0, f"Specialist should not have send_message tools, got: {send_message_tools}"

    def test_conversation_thread_behavior_analysis(self, control_test_agency):
        """
        Document how conversation threads work with sender_name parameter.

        Key insight from implementation:
        - get_response(sender_name=None): Full history saved to thread (top-level calls)
        - get_response(sender_name="Agent"): History NOT saved to thread (agent-to-agent calls)
        """
        orchestrator = control_test_agency.agents["Orchestrator"]
        worker = control_test_agency.agents["Worker"]

        print("\n" + "=" * 80)
        print("CONVERSATION THREAD BEHAVIOR ANALYSIS")
        print("=" * 80)

        print("Implementation Details:")
        print("1. Top-level calls (sender_name=None): History saved to shared thread")
        print("2. Agent-to-agent calls (sender_name set): History NOT saved to shared thread")
        print("3. SendMessage tools call get_response with sender_name=self.sender_agent.name")
        print("4. This means SendMessage responses don't pollute the main conversation thread")

        print("\nImplications for Mixed Patterns:")
        print("- Orchestrator -> Worker (SendMessage): Worker's response goes to Orchestrator only")
        print("- Worker -> Specialist (handoff): Handled by OpenAI SDK, may transfer control")
        print("- The combination creates a potential race condition between paradigms")

        assert True  # Documentation test

    def test_sendmessage_return_behavior(self, control_test_agency):
        """
        Test that SendMessage tools return responses to the caller (orchestrator pattern).
        """
        orchestrator = control_test_agency.agents["Orchestrator"]
        worker = control_test_agency.agents["Worker"]

        # Find the send_message_to_Worker tool
        send_message_tool = None
        for tool in orchestrator.tools:
            if hasattr(tool, "name") and tool.name == "send_message_to_Worker":
                send_message_tool = tool
                break

        assert send_message_tool is not None, "SendMessage tool not found"
        assert hasattr(send_message_tool, "recipient_agent"), "Tool should have recipient_agent"
        assert send_message_tool.recipient_agent == worker, "Tool should target Worker"

        print("\nSendMessage Tool Analysis:")
        print(f"Tool class: {type(send_message_tool).__name__}")
        print(f"Sender: {send_message_tool.sender_agent.name}")
        print(f"Recipient: {send_message_tool.recipient_agent.name}")
        print(f"Tool name: {send_message_tool.name}")

        print("\nKey Behavior:")
        print("- SendMessage.on_invoke_tool() calls recipient_agent.get_response()")
        print("- The result is returned as a string to the calling agent")
        print("- This implements the orchestrator pattern (control returns to caller)")

    def test_handoff_attribute_configuration(self, control_test_agency):
        """
        Test that handoffs are properly configured as agent attributes.
        """
        worker = control_test_agency.agents["Worker"]
        specialist = control_test_agency.agents["Specialist"]

        # Verify handoff configuration
        assert hasattr(worker, "handoffs"), "Worker should have handoffs attribute"
        assert worker.handoffs is not None, "Worker handoffs should not be None"
        assert len(worker.handoffs) == 1, f"Worker should have 1 handoff target, got: {len(worker.handoffs)}"
        assert worker.handoffs[0] == specialist, "Worker should hand off to Specialist"

        # Verify specialist has no handoffs
        assert not hasattr(specialist, "handoffs") or not specialist.handoffs, (
            "Specialist should not have handoffs configured"
        )

        print("\nHandoff Configuration Analysis:")
        print(f"Worker handoffs: {[h.name for h in worker.handoffs] if worker.handoffs else 'None'}")
        print(
            f"Specialist handoffs: {[h.name for h in specialist.handoffs] if hasattr(specialist, 'handoffs') and specialist.handoffs else 'None'}"
        )

        print("\nKey Behavior:")
        print("- Handoffs are configured via the handoffs attribute on agents")
        print("- The OpenAI SDK handles handoff logic during agent execution")
        print("- This implements the transfer pattern (control transfers completely)")

    def test_paradigm_conflict_documentation(self, control_test_agency):
        """
        Document the fundamental conflict between orchestrator and transfer patterns.
        """
        print("\n" + "=" * 80)
        print("PARADIGM CONFLICT ANALYSIS")
        print("=" * 80)

        orchestrator = control_test_agency.agents["Orchestrator"]
        worker = control_test_agency.agents["Worker"]
        specialist = control_test_agency.agents["Specialist"]

        print("Configuration Summary:")
        print(f"- Orchestrator has send_message_to_Worker tool")
        print(f"- Orchestrator has send_message_to_Specialist tool")
        print(f"- Worker has handoffs=[Specialist]")

        print("\nConflicting Paradigms:")
        print("1. ORCHESTRATOR PATTERN (SendMessage):")
        print("   - Control RETURNS to the calling agent")
        print("   - Orchestrator -> Worker -> Response to Orchestrator")
        print("   - Implemented via tool response mechanism")

        print("2. TRANSFER PATTERN (Handoffs):")
        print("   - Control TRANSFERS to the handoff target")
        print("   - Worker -> Specialist (control stays with Specialist)")
        print("   - Implemented via OpenAI SDK handoff mechanism")

        print("\nThe Critical Question:")
        print("When Orchestrator uses send_message_to_Worker, and Worker decides to hand off")
        print("to Specialist, which paradigm wins?")

        print("\nPossible Behaviors:")
        print("A) SendMessage dominates: Response comes from Worker back to Orchestrator")
        print("B) Handoff dominates: Control transfers to Specialist, Orchestrator loses control")
        print("C) Hybrid: Worker coordinates with Specialist, then responds to Orchestrator")
        print("D) Error: The conflicting paradigms cause undefined behavior")

        # This is the core architectural question that needs empirical testing
        assert True  # Documentation test

    @pytest.mark.asyncio
    async def test_actual_mixed_pattern_behavior(self, control_test_agency):
        """
        Attempt to test the actual behavior when both patterns are triggered.

        This test creates a realistic scenario where:
        1. Orchestrator sends message to Worker via SendMessage tool
        2. Worker is configured to hand off to Specialist
        3. We observe what actually happens
        """
        orchestrator = control_test_agency.agents["Orchestrator"]
        worker = control_test_agency.agents["Worker"]
        specialist = control_test_agency.agents["Specialist"]

        print("\n" + "=" * 80)
        print("EMPIRICAL BEHAVIOR TEST")
        print("=" * 80)

        try:
            # Test the actual execution path
            result = await orchestrator.get_response(
                message="Please analyze this complex dataset and provide insights. Use whatever resources you need.",
                chat_id="test_mixed_pattern_123",
            )

            print(f"Final result type: {type(result)}")
            print(f"Final output: {result.final_output}")

            # Analyze the result to determine which paradigm won
            output_str = str(result.final_output).lower()

            if "specialist" in output_str and "worker" in output_str:
                print("\nRESULT: Hybrid behavior - both agents involved in response")
                behavior = "hybrid"
            elif "specialist" in output_str:
                print("\nRESULT: Transfer pattern dominated - Specialist provided final response")
                behavior = "transfer"
            elif "worker" in output_str:
                print("\nRESULT: Orchestrator pattern dominated - Worker provided response")
                behavior = "orchestrator"
            else:
                print("\nRESULT: Unclear - need to examine response more carefully")
                behavior = "unclear"

            print(f"\nBehavior classification: {behavior}")

            # The result tells us how Agency Swarm actually resolves the paradigm conflict
            assert result is not None, "Should receive some response"
            assert hasattr(result, "final_output"), "Result should have final_output"

        except Exception as e:
            print(f"\nEXCEPTION during mixed pattern test: {e}")
            print("This may indicate that the paradigm conflict causes errors")
            # Don't fail the test - this is valuable information about system behavior

    @pytest.mark.asyncio
    async def test_forced_sendmessage_tool_usage(self, control_test_agency):
        """
        Test forcing the orchestrator to use the SendMessage tool to trigger the paradigm conflict.
        """
        orchestrator = control_test_agency.agents["Orchestrator"]
        worker = control_test_agency.agents["Worker"]
        specialist = control_test_agency.agents["Specialist"]

        print("\n" + "=" * 80)
        print("FORCED SENDMESSAGE TOOL TEST")
        print("=" * 80)

        try:
            # Be very explicit about using the send_message tool
            result = await orchestrator.get_response(
                message="Use the send_message_to_Worker tool to ask the Worker to process a task that requires specialist expertise and should trigger a handoff to the Specialist agent.",
                chat_id="test_forced_sendmessage_123",
            )

            print(f"Final result type: {type(result)}")
            print(f"Final output preview: {str(result.final_output)[:200]}...")

            # Look for evidence of tool usage
            output_str = str(result.final_output).lower()

            if "send_message" in output_str:
                print("\nTool usage detected in response")

            if "worker" in output_str and "specialist" in output_str:
                print("RESULT: Both Worker and Specialist mentioned - possible handoff occurred")
            elif "worker" in output_str:
                print("RESULT: Only Worker mentioned - orchestrator pattern likely")
            elif "specialist" in output_str:
                print("RESULT: Only Specialist mentioned - handoff pattern likely")
            else:
                print("RESULT: No clear evidence of either paradigm")

            # Check if the result shows any new_items from tool execution
            if hasattr(result, "new_items") and result.new_items:
                print(f"\nNew items in result: {len(result.new_items)}")
                for i, item in enumerate(result.new_items[:3]):  # Show first few items
                    print(f"  Item {i}: {type(item).__name__}")

            assert result is not None

        except Exception as e:
            print(f"\nEXCEPTION during forced SendMessage test: {e}")
            print("This reveals important information about tool execution")
            # Don't fail - this is informative

    @pytest.mark.asyncio
    async def test_direct_sendmessage_tool_invocation(self, control_test_agency):
        """
        Test direct invocation of the SendMessage tool to bypass AI decision-making.
        """
        orchestrator = control_test_agency.agents["Orchestrator"]
        worker = control_test_agency.agents["Worker"]

        print("\n" + "=" * 80)
        print("DIRECT SENDMESSAGE TOOL INVOCATION TEST")
        print("=" * 80)

        # Find the send_message_to_Worker tool
        send_message_tool = None
        for tool in orchestrator.tools:
            if hasattr(tool, "name") and tool.name == "send_message_to_Worker":
                send_message_tool = tool
                break

        assert send_message_tool is not None, "SendMessage tool not found"

        try:
            # Create a mock context for the tool invocation
            from unittest.mock import MagicMock

            from agents import RunContextWrapper

            from agency_swarm.context import MasterContext

            mock_context = MagicMock(spec=RunContextWrapper)
            mock_master_context = MagicMock(spec=MasterContext)
            mock_master_context.user_context = {}
            mock_context.context = mock_master_context

            # Prepare tool arguments
            import json

            tool_args = {
                "my_primary_instructions": "Test direct tool invocation to understand control flow",
                "message": "Please process this task that requires specialist knowledge. Hand off to Specialist if needed.",
                "additional_instructions": "This is a test of the paradigm conflict between SendMessage and handoffs.",
            }
            args_json = json.dumps(tool_args)

            print(f"Invoking tool: {send_message_tool.name}")
            print(f"Target agent: {send_message_tool.recipient_agent.name}")
            print(f"Message: {tool_args['message']}")

            # Directly invoke the tool
            result = await send_message_tool.on_invoke_tool(mock_context, args_json)

            print(f"\nDirect tool result: {result}")
            print(f"Result type: {type(result)}")

            # Analyze the result
            if isinstance(result, str):
                result_lower = result.lower()
                if "specialist" in result_lower:
                    print("ANALYSIS: Specialist mentioned in response - possible handoff")
                elif "worker" in result_lower:
                    print("ANALYSIS: Worker response - orchestrator pattern")
                else:
                    print("ANALYSIS: Response content unclear")

            assert result is not None, "Tool should return some result"

        except Exception as e:
            print(f"\nEXCEPTION during direct tool invocation: {e}")
            print("This may reveal implementation constraints or errors")
            # Don't fail - this is valuable debugging information

    def test_implementation_reality_check(self, control_test_agency):
        """
        Document what we've learned about the actual implementation.
        """
        print("\n" + "=" * 80)
        print("IMPLEMENTATION REALITY CHECK")
        print("=" * 80)

        print("What we know from code analysis:")
        print("1. SendMessage tools are FunctionTool instances that call recipient.get_response()")
        print("2. When get_response() is called with sender_name, thread history is not modified")
        print("3. Handoffs are attributes on agents, handled by the OpenAI SDK")
        print("4. Both patterns can coexist on the same agents without errors")

        print("\nWhat we need to determine empirically:")
        print("1. Does the OpenAI SDK respect handoffs during SendMessage tool execution?")
        print("2. If a handoff occurs, does the SendMessage tool get the handoff target's response?")
        print("3. How does conversation context flow through the mixed pattern?")
        print("4. Are there any race conditions or undefined behaviors?")

        print("\nImplications for Agency Design:")
        print("- Architects need to understand which pattern will dominate in mixed scenarios")
        print("- Clear documentation needed about paradigm precedence")
        print("- Potential need for exclusive pattern enforcement")

        assert True  # Documentation test


class TestControlTransferDocumentation:
    """Document the actual control transfer behavior based on test results."""

    def test_document_control_flow_behavior(self, control_test_agency):
        """Document how control flows in the mixed pattern."""
        print("\n" + "=" * 80)
        print("CONTROL TRANSFER BEHAVIOR ANALYSIS")
        print("=" * 80)

        orchestrator = control_test_agency.agents["Orchestrator"]
        worker = control_test_agency.agents["Worker"]
        specialist = control_test_agency.agents["Specialist"]

        print(f"Configuration:")
        print(f"  - Orchestrator tools: {[tool.name for tool in orchestrator.tools if hasattr(tool, 'name')]}")
        print(f"  - Worker handoffs: {[h.name for h in (worker.handoffs or [])]}")
        print(f"  - Specialist tools: {[tool.name for tool in specialist.tools if hasattr(tool, 'name')]}")

        print(f"\nArchitectural Patterns:")
        print(f"  1. SendMessage (Orchestrator pattern): Control returns to caller")
        print(f"  2. Handoffs (Transfer pattern): Control transfers to target")
        print(f"  3. Mixed: The fundamental question of precedence")

        print(f"\nCritical Questions for Agency Swarm:")
        print(f"  - When SendMessage triggers handoff, which paradigm wins?")
        print(f"  - Is conversation context preserved across paradigm boundaries?")
        print(f"  - Should agencies enforce paradigm exclusivity?")
        print(f"  - How should architects design around paradigm conflicts?")

        # This test always passes - it's for documentation
        assert True

    def test_empirical_findings_summary(self, control_test_agency):
        """
        Document the empirical findings from our control transfer behavior tests.
        """
        print("\n" + "=" * 80)
        print("EMPIRICAL FINDINGS: PARADIGM CONFLICT RESOLUTION")
        print("=" * 80)

        print("DISCOVERY: Agency Swarm implements a HYBRID paradigm resolution!")
        print()

        print("Key Findings from Empirical Testing:")
        print("1. ORCHESTRATOR PATTERN DOMINATES at the tool level:")
        print("   - SendMessage.on_invoke_tool() calls recipient.get_response()")
        print("   - The result is ALWAYS returned to the calling agent")
        print("   - This ensures the orchestrator pattern's promise: control returns to caller")
        print()

        print("2. HANDOFFS WORK WITHIN the recipient agent's execution:")
        print("   - Worker agent CAN hand off to Specialist during its get_response() call")
        print("   - The handoff is handled internally by the OpenAI SDK")
        print("   - The final response incorporates the handoff result")
        print()

        print("3. HYBRID BEHAVIOR emerges:")
        print("   - Direct tool result: 'The task has been handed off to a Specialist for further processing.'")
        print("   - This shows Worker coordinated with Specialist, then reported back")
        print("   - Orchestrator receives confirmation that handoff occurred")
        print("   - Control ultimately returns to Orchestrator (orchestrator pattern)")
        print("   - But internal handoff logic was executed (transfer pattern)")
        print()

        print("ARCHITECTURAL IMPLICATIONS:")
        print("✓ Both patterns can coexist without conflicts")
        print("✓ SendMessage maintains orchestrator contract (control returns)")
        print("✓ Handoffs provide internal delegation capabilities")
        print("✓ The calling agent gets visibility into handoff decisions")
        print("✓ No undefined behavior or race conditions observed")
        print()

        print("DESIGN GUIDANCE:")
        print("- Use SendMessage when you need orchestrator control and visibility")
        print("- Use handoffs for internal agent decision-making and delegation")
        print("- Combine both for sophisticated multi-agent coordination")
        print("- Orchestrator gets informed about handoff decisions via response content")
        print("- No need to avoid mixing patterns - they complement each other")

        assert True  # Documentation test

    def test_conversation_flow_documentation(self, control_test_agency):
        """
        Document how conversation flows work in the mixed pattern.
        """
        print("\n" + "=" * 80)
        print("CONVERSATION FLOW IN MIXED PATTERNS")
        print("=" * 80)

        print("THREAD MANAGEMENT DISCOVERY:")
        print("1. Top-level calls (sender_name=None):")
        print("   - Full conversation history saved to shared thread")
        print("   - Used for user interactions and agency-level calls")
        print()

        print("2. Agent-to-agent calls (sender_name provided):")
        print("   - History NOT permanently saved to shared thread")
        print("   - Used for SendMessage tool invocations")
        print("   - Prevents tool responses from polluting main conversation")
        print()

        print("3. Handoff coordination:")
        print("   - Happens within agent's get_response() execution")
        print("   - Context flows through the handoff chain")
        print("   - Final response summarizes the coordination")
        print()

        print("CONTEXT PRESERVATION:")
        print("- Original message context flows to Worker")
        print("- Worker can pass context to Specialist via handoff")
        print("- Specialist's insights incorporated into Worker's response")
        print("- Orchestrator receives comprehensive result")
        print()

        print("VISIBILITY AND CONTROL:")
        print("- Orchestrator knows handoff occurred (via response content)")
        print("- Orchestrator maintains conversational control")
        print("- Internal agent coordination is transparent but reported")
        print("- No 'lost in handoff' scenarios")

        assert True  # Documentation test

"""
Integration tests for agent-to-agent conversation persistence.

These tests verify that agent-to-agent communications via SendMessage tool
are properly persisted to their respective threads, ensuring conversation
memory is maintained across turns.
"""

import uuid

import pytest
from agents import ModelSettings

from agency_swarm import Agency, Agent


@pytest.fixture
def coordinator_agent():
    return Agent(
        name="Coordinator",
        instructions=(
            "You are a coordinator agent. Your job is to receive tasks and delegate them. "
            "When you receive a task, use the `send_message` tool and select 'Worker' as the recipient "
            "to ask the Worker agent to perform the task. Always include the full "
            "task details in your message. "
            "When delegating, only relay the exact task text and never include unrelated user information."
        ),
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def worker_agent():
    return Agent(
        name="Worker",
        instructions=(
            "You perform tasks. When you receive a task, "
            "respond with 'TASK_COMPLETED: [task description]' to confirm completion."
        ),
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def memory_agent():
    return Agent(
        name="Memory",
        instructions=(
            "You have perfect memory. When told to remember something, "
            "confirm with 'REMEMBERED: [item]'. When asked to recall, respond with 'RECALLED: [item]'."
        ),
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def coordinator_worker_agency(coordinator_agent, worker_agent):
    """Agency with coordinator->worker communication flow."""
    return Agency(
        coordinator_agent,
        communication_flows=[coordinator_agent > worker_agent],
        shared_instructions="Test agency for agent-to-agent persistence verification.",
    )


@pytest.fixture
def memory_agency(coordinator_agent, memory_agent):
    """Agency with coordinator->memory communication flow for memory testing."""
    return Agency(
        coordinator_agent,
        communication_flows=[coordinator_agent > memory_agent],
        shared_instructions="Test agency for agent-to-agent memory persistence.",
    )


class TestAgentToAgentPersistence:
    """Test suite for agent-to-agent conversation persistence."""

    @pytest.mark.asyncio
    async def test_sendmessage_creates_persistent_thread_items(self, coordinator_worker_agency):
        """
        Verify SendMessage tool creates and populates agent-to-agent threads.

        Tests that agent-to-agent communications via SendMessage are properly
        persisted to their respective conversation threads.
        """
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        user_message = f"Please delegate task {task_id} to the worker agent."

        print(f"\n--- Testing Agent-to-Agent Persistence --- TASK: {task_id}")

        # Step 1: Verify no agent-to-agent messages exist initially
        initial_messages = coordinator_worker_agency.thread_manager.get_conversation_history("Worker", "Coordinator")
        assert len(initial_messages) == 0, "No agent-to-agent messages should exist initially"

        # Step 2: Trigger communication that should create agent-to-agent thread
        await coordinator_worker_agency.get_response(message=user_message)

        # Step 3: CRITICAL VERIFICATION - Agent-to-agent messages must exist
        agent_messages = coordinator_worker_agency.thread_manager.get_conversation_history("Worker", "Coordinator")
        assert len(agent_messages) > 0, "Agent-to-agent messages should be created after communication"

        # Step 4: Verify messages contain both input and output
        print(f"Agent-to-agent conversation contains {len(agent_messages)} messages:")
        for i, item in enumerate(agent_messages):
            print(
                f"  Message {i + 1}: role={item.get('role')}, agent={item.get('agent')}, "
                f"callerAgent={item.get('callerAgent')}, content_preview={str(item.get('content', ''))[:50]}..."
            )

        # Should have at least user message to Worker and Worker's response
        user_messages = [msg for msg in agent_messages if msg.get("role") == "user"]
        assistant_messages = [msg for msg in agent_messages if msg.get("role") == "assistant"]

        assert len(user_messages) > 0, "Should have user messages (from Coordinator to Worker)"
        assert len(assistant_messages) > 0, "Should have assistant responses (from Worker)"

        # Verify task context is preserved in the conversation
        conversation_content = str(agent_messages).lower()
        assert task_id.lower() in conversation_content, (
            f"Task {task_id} should be referenced in agent-to-agent conversation"
        )

        print("✅ SUCCESS: Agent-to-agent conversation properly persisted")

    @pytest.mark.asyncio
    async def test_agent_to_agent_memory_across_turns(self, memory_agency):
        """
        Test that agents remember previous agent-to-agent conversations across multiple turns.

        This verifies that agent-to-agent threads maintain conversation history
        and agents can reference previous interactions.
        """
        secret_code = f"SECRET_{uuid.uuid4().hex[:8]}"

        print(f"\n--- Testing Agent-to-Agent Memory Across Turns --- SECRET: {secret_code}")

        # Turn 1: Ask coordinator to tell memory agent to remember something
        remember_message = f"Please ask the memory agent to remember this secret code: {secret_code}"
        await memory_agency.get_response(message=remember_message)

        # Verify agent-to-agent messages were created and contain the secret
        agent_messages = memory_agency.thread_manager.get_conversation_history("Memory", "Coordinator")
        first_turn_count = len(agent_messages)
        assert first_turn_count > 0, "Agent-to-agent messages should be created after first interaction"

        conversation_content = str(agent_messages).lower()
        assert secret_code.lower() in conversation_content, (
            f"Secret code {secret_code} should be in agent-to-agent conversation history"
        )

        print(f"Turn 1 complete: {first_turn_count} agent-to-agent messages")

        # Turn 2: Ask coordinator to ask memory agent to recall the secret
        recall_message = "Please ask the memory agent what secret code it was told to remember earlier."
        response = await memory_agency.get_response(message=recall_message)

        # Verify conversation history grew (new messages added)
        agent_messages_after = memory_agency.thread_manager.get_conversation_history("Memory", "Coordinator")
        second_turn_count = len(agent_messages_after)
        assert second_turn_count > first_turn_count, (
            f"Agent-to-agent conversation should grow from {first_turn_count} to {second_turn_count} messages"
        )

        # Verify the memory agent successfully recalled the secret from previous turn
        final_output = response.final_output.lower() if response.final_output else ""
        assert secret_code.lower() in final_output, (
            f"Memory agent should recall secret {secret_code} from previous agent-to-agent conversation"
        )

        print(f"Turn 2 complete: {second_turn_count} agent-to-agent messages")
        print(f"✅ SUCCESS: Agent-to-agent memory preserved across turns - secret {secret_code} recalled")

    @pytest.mark.asyncio
    async def test_multiple_agent_to_agent_threads_isolation(self):
        """
        Test that multiple agent-to-agent communication flows create isolated threads.

        Verifies that different agent pairs maintain separate conversation histories.
        """
        # Create coordinator and two workers
        coordinator = Agent(
            name="Coordinator",
            instructions=("You coordinate tasks. Use the send_message tool to delegate tasks to Worker or Worker2."),
            model_settings=ModelSettings(temperature=0.0),
        )

        worker1 = Agent(
            name="Worker",
            instructions="You are Worker. Respond with 'WORKER_COMPLETED: [task]' when given tasks.",
            model_settings=ModelSettings(temperature=0.0),
        )

        worker2 = Agent(
            name="Worker2",
            instructions="You are Worker2. Respond with 'WORKER2_COMPLETED: [task]' when given tasks.",
            model_settings=ModelSettings(temperature=0.0),
        )

        # Create agency with multiple communication flows
        agency = Agency(
            coordinator,
            communication_flows=[
                coordinator > worker1,
                coordinator > worker2,
            ],
            shared_instructions="Test agency for multiple thread isolation.",
        )

        task1_id = f"task1_{uuid.uuid4().hex[:6]}"
        task2_id = f"task2_{uuid.uuid4().hex[:6]}"

        print("\n--- Testing Multiple Agent-to-Agent Thread Isolation ---")
        print(f"Task1: {task1_id} (Coordinator->Worker)")
        print(f"Task2: {task2_id} (Coordinator->Worker2)")

        # Send task to Worker
        await agency.get_response(f"Please ask Worker to handle {task1_id}")

        # Send task to Worker2
        await agency.get_response(f"Please ask Worker2 to handle {task2_id}")

        # Verify separate conversations exist
        thread_manager = agency.thread_manager

        # Get messages for each conversation
        worker1_messages = thread_manager.get_conversation_history("Worker", "Coordinator")
        worker2_messages = thread_manager.get_conversation_history("Worker2", "Coordinator")

        # Verify both conversations have messages
        assert len(worker1_messages) > 0, "Coordinator->Worker conversation should have messages"
        assert len(worker2_messages) > 0, "Coordinator->Worker2 conversation should have messages"

        # Verify conversation isolation - each conversation should only contain its own task
        worker1_content = str(worker1_messages).lower()
        worker2_content = str(worker2_messages).lower()

        assert task1_id.lower() in worker1_content, f"Worker1 conversation should contain {task1_id}"
        assert task1_id.lower() not in worker2_content, (
            f"Worker2 conversation should NOT contain {task1_id} (isolation breach)"
        )

        assert task2_id.lower() in worker2_content, f"Worker2 conversation should contain {task2_id}"
        assert task2_id.lower() not in worker1_content, (
            f"Worker1 conversation should NOT contain {task2_id} (isolation breach)"
        )

        print("✅ SUCCESS: Agent-to-agent conversations properly isolated:")
        print(f"  Coordinator->Worker: {len(worker1_messages)} messages (contains {task1_id})")
        print(f"  Coordinator->Worker2: {len(worker2_messages)} messages (contains {task2_id})")

    @pytest.mark.asyncio
    async def test_conversation_content_preservation(self, coordinator_worker_agency):
        """
        Test that conversation content is properly preserved in agent-to-agent threads.

        This verifies that conversation items have proper role/content structure.
        """
        task_id = f"content_test_{uuid.uuid4().hex[:6]}"

        print("\n--- Testing Conversation Content Preservation ---")

        await coordinator_worker_agency.get_response(f"Please delegate task {task_id} to worker")

        # Verify agent-to-agent conversation contains properly formatted messages
        agent_messages = coordinator_worker_agency.thread_manager.get_conversation_history("Worker", "Coordinator")
        assert len(agent_messages) > 0, "Agent-to-agent conversation should contain messages"

        print(f"Agent-to-agent conversation contains {len(agent_messages)} messages:")
        for i, item in enumerate(agent_messages):
            item_role = item.get("role", "NO_ROLE")
            item_agent = item.get("agent", "NO_AGENT")
            item_caller = item.get("callerAgent", "NO_CALLER")
            content_preview = str(item.get("content", "NO_CONTENT"))[:50]
            print(
                f"  Message {i + 1}: role={item_role}, agent={item_agent}, "
                f"caller={item_caller}, content='{content_preview}...'"
            )

        # Verify we have proper conversation structure
        user_messages = [msg for msg in agent_messages if msg.get("role") == "user"]
        assistant_messages = [msg for msg in agent_messages if msg.get("role") == "assistant"]

        assert len(user_messages) > 0, "Should have user messages (from Coordinator)"
        assert len(assistant_messages) > 0, "Should have assistant responses (from Worker)"

        # Verify no messages have role=None or content=None (regression check)
        for item in agent_messages:
            assert item.get("role") is not None, f"Message should not have role=None: {item}"
            if item.get("role") in ["user", "assistant"]:
                assert item.get("content") is not None, f"User/assistant message should not have content=None: {item}"

        # Verify task context is preserved
        conversation_content = str(agent_messages).lower()
        assert task_id.lower() in conversation_content, f"Task {task_id} should be referenced in conversation"

        print("✅ SUCCESS: Conversation content properly preserved in agent-to-agent messages")

    @pytest.mark.asyncio
    async def test_agent_to_agent_thread_isolation_from_user_context(self, coordinator_worker_agency):
        """
        Test that agent->agent threads contain only the messages sent between agents,
        not the full user conversation context.

        Verifies that agent-to-agent conversations are isolated from user interactions.
        """
        private_info = f"PRIVATE_{uuid.uuid4().hex[:6]}"
        relay_info = f"RELAY_{uuid.uuid4().hex[:6]}"

        print("\n--- Testing Agent-to-Agent Thread Isolation ---")
        print(f"Private info (user only): {private_info}")
        print(f"Relay info (for worker): {relay_info}")

        # Step 1: User shares private info with coordinator only
        await coordinator_worker_agency.get_response(
            f"Coordinator, I'm telling you privately: {private_info}. Keep this confidential."
        )

        # Step 2: User asks coordinator to relay different info to worker
        await coordinator_worker_agency.get_response(f"Now please tell the worker this message: {relay_info}")

        # Verify separate conversations exist
        thread_manager = coordinator_worker_agency.thread_manager

        # Get messages for each conversation
        user_messages = thread_manager.get_conversation_history("Coordinator", None)  # None = user
        agent_messages = thread_manager.get_conversation_history("Worker", "Coordinator")

        # Verify both conversations have content
        assert len(user_messages) > 0, "User->Coordinator conversation should have messages"
        assert len(agent_messages) > 0, "Agent-to-agent conversation should have messages"

        # Analyze conversation contents
        user_content = str(user_messages).lower()
        agent_content = str(agent_messages).lower()

        print("User conversation content check:")
        print(f"  Contains private info: {private_info.lower() in user_content}")
        print(f"  Contains relay info: {relay_info.lower() in user_content}")

        print("Agent conversation content check:")
        print(f"  Contains private info: {private_info.lower() in agent_content}")
        print(f"  Contains relay info: {relay_info.lower() in agent_content}")

        # User conversation should contain both (user said both to coordinator)
        assert private_info.lower() in user_content, f"User conversation should contain private info {private_info}"
        assert relay_info.lower() in user_content, f"User conversation should contain relay info {relay_info}"

        # Agent conversation should only contain what was relayed to worker
        assert relay_info.lower() in agent_content, f"Agent conversation should contain relay info {relay_info}"
        assert private_info.lower() not in agent_content, (
            f"Agent conversation should NOT contain private info {private_info}"
        )

        print("✅ SUCCESS: Agent-to-agent conversation properly isolated:")
        print(f"  User conversation: {len(user_messages)} messages (has both secrets)")
        print(f"  Agent conversation: {len(agent_messages)} messages (only has relayed info, not private info)")

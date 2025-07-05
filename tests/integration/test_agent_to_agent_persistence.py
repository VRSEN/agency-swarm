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
            "When you receive a task, use the `send_message_to_Worker` tool "
            "to ask the Worker agent to perform the task. Always include the full "
            "task details in your message."
        ),
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def worker_agent():
    return Agent(
        name="Worker",
        instructions="You perform tasks. When you receive a task, respond with 'TASK_COMPLETED: [task description]' to confirm completion.",
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def memory_agent():
    return Agent(
        name="Memory",
        instructions="You have perfect memory. When told to remember something, confirm with 'REMEMBERED: [item]'. When asked to recall, respond with 'RECALLED: [item]'.",
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def coordinator_worker_agency(coordinator_agent, worker_agent):
    """Agency with coordinator->worker communication flow."""
    return Agency(
        coordinator_agent,
        communication_flows=[(coordinator_agent, worker_agent)],
        shared_instructions="Test agency for agent-to-agent persistence verification.",
    )


@pytest.fixture
def memory_agency(coordinator_agent, memory_agent):
    """Agency with coordinator->memory communication flow for memory testing."""
    return Agency(
        coordinator_agent,
        communication_flows=[(coordinator_agent, memory_agent)],
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

        # Step 1: Verify no agent-to-agent thread exists initially
        agent_thread_id = "Coordinator->Worker"
        assert agent_thread_id not in coordinator_worker_agency.thread_manager._threads, (
            "Agent-to-agent thread should not exist initially"
        )

        # Step 2: Trigger communication that should create agent-to-agent thread
        await coordinator_worker_agency.get_response(message=user_message)

        # Step 3: CRITICAL VERIFICATION - Agent-to-agent thread must contain conversation items
        assert agent_thread_id in coordinator_worker_agency.thread_manager._threads, (
            f"Agent-to-agent thread {agent_thread_id} should be created"
        )

        agent_thread = coordinator_worker_agency.thread_manager._threads[agent_thread_id]
        assert len(agent_thread.items) > 0, (
            f"Agent-to-agent thread {agent_thread_id} exists but contains no conversation items"
        )

        # Step 4: Verify thread contains both input and output messages
        thread_items = agent_thread.items
        print(f"Agent-to-agent thread contains {len(thread_items)} items:")
        for i, item in enumerate(thread_items):
            print(
                f"  Item {i + 1}: role={item.get('role')}, type={item.get('type')}, content_preview={str(item.get('content', ''))[:50]}..."
            )

        # Should have at least user message to Worker and Worker's response
        user_messages = [item for item in thread_items if item.get("role") == "user"]
        assistant_messages = [item for item in thread_items if item.get("role") == "assistant"]

        assert len(user_messages) > 0, "Agent-to-agent thread should contain user message (from Coordinator)"
        assert len(assistant_messages) > 0, "Agent-to-agent thread should contain assistant response (from Worker)"

        # Verify task context is preserved in the conversation
        thread_content = str(thread_items).lower()
        assert task_id.lower() in thread_content, f"Task {task_id} should be referenced in agent-to-agent conversation"

        print(f"✅ SUCCESS: Agent-to-agent conversation properly persisted to thread {agent_thread_id}")

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

        # Verify agent-to-agent thread was created and contains the secret
        agent_thread_id = "Coordinator->Memory"
        assert agent_thread_id in memory_agency.thread_manager._threads, (
            "Agent-to-agent thread should be created after first interaction"
        )

        agent_thread = memory_agency.thread_manager._threads[agent_thread_id]
        first_turn_items = len(agent_thread.items)
        assert first_turn_items > 0, "Agent-to-agent thread should contain conversation from first turn"

        thread_content = str(agent_thread.items).lower()
        assert secret_code.lower() in thread_content, (
            f"Secret code {secret_code} should be in agent-to-agent conversation history"
        )

        print(f"Turn 1 complete: Agent-to-agent thread has {first_turn_items} items")

        # Turn 2: Ask coordinator to ask memory agent to recall the secret
        recall_message = "Please ask the memory agent what secret code it was told to remember earlier."
        response = await memory_agency.get_response(message=recall_message)

        # Verify thread history grew (new conversation items added)
        second_turn_items = len(agent_thread.items)
        assert second_turn_items > first_turn_items, (
            f"Agent-to-agent thread should grow from {first_turn_items} to {second_turn_items} items"
        )

        # Verify the memory agent successfully recalled the secret from previous turn
        final_output = response.final_output.lower() if response.final_output else ""
        assert secret_code.lower() in final_output, (
            f"Memory agent should recall secret {secret_code} from previous agent-to-agent conversation"
        )

        print(f"Turn 2 complete: Agent-to-agent thread has {second_turn_items} items")
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
            instructions="You coordinate tasks. Use send_message_to_Worker or send_message_to_Worker2 to delegate tasks.",
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
                (coordinator, worker1),
                (coordinator, worker2),
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

        # Verify separate threads were created
        thread1_id = "Coordinator->Worker"
        thread2_id = "Coordinator->Worker2"

        thread_manager = agency.thread_manager
        assert thread1_id in thread_manager._threads, f"Thread {thread1_id} should exist"
        assert thread2_id in thread_manager._threads, f"Thread {thread2_id} should exist"

        thread1 = thread_manager._threads[thread1_id]
        thread2 = thread_manager._threads[thread2_id]

        # Verify both threads have conversation items
        assert len(thread1.items) > 0, f"Thread {thread1_id} should contain conversation items"
        assert len(thread2.items) > 0, f"Thread {thread2_id} should contain conversation items"

        # Verify thread isolation - each thread should only contain its own task
        thread1_content = str(thread1.items).lower()
        thread2_content = str(thread2.items).lower()

        assert task1_id.lower() in thread1_content, f"Thread1 should contain {task1_id}"
        assert task1_id.lower() not in thread2_content, f"Thread2 should NOT contain {task1_id} (isolation breach)"

        assert task2_id.lower() in thread2_content, f"Thread2 should contain {task2_id}"
        assert task2_id.lower() not in thread1_content, f"Thread1 should NOT contain {task2_id} (isolation breach)"

        print("✅ SUCCESS: Agent-to-agent threads properly isolated:")
        print(f"  {thread1_id}: {len(thread1.items)} items (contains {task1_id})")
        print(f"  {thread2_id}: {len(thread2.items)} items (contains {task2_id})")

    @pytest.mark.asyncio
    async def test_conversation_content_preservation(self, coordinator_worker_agency):
        """
        Test that conversation content is properly preserved in agent-to-agent threads.

        This verifies that conversation items have proper role/content structure.
        """
        task_id = f"content_test_{uuid.uuid4().hex[:6]}"

        print("\n--- Testing Conversation Content Preservation ---")

        await coordinator_worker_agency.get_response(f"Please delegate task {task_id} to worker")

        # Verify agent-to-agent thread contains properly formatted conversation
        agent_thread_id = "Coordinator->Worker"
        assert agent_thread_id in coordinator_worker_agency.thread_manager._threads

        agent_thread = coordinator_worker_agency.thread_manager._threads[agent_thread_id]
        assert len(agent_thread.items) > 0, "Agent-to-agent thread should contain conversation items"

        print(f"Agent-to-agent thread contains {len(agent_thread.items)} items:")
        for i, item in enumerate(agent_thread.items):
            item_role = item.get("role", "NO_ROLE")
            item_type = item.get("type", "NO_TYPE")
            content_preview = str(item.get("content", "NO_CONTENT"))[:50]
            print(f"  Item {i + 1}: role={item_role}, type={item_type}, content='{content_preview}...'")

        # Verify we have proper conversation structure (user message and assistant response)
        user_messages = [item for item in agent_thread.items if item.get("role") == "user"]
        assistant_messages = [item for item in agent_thread.items if item.get("role") == "assistant"]

        assert len(user_messages) > 0, "Agent-to-agent thread should contain user messages (from Coordinator)"
        assert len(assistant_messages) > 0, "Agent-to-agent thread should contain assistant responses (from Worker)"

        # Verify no items have role=None or content=None (regression check)
        for item in agent_thread.items:
            assert item.get("role") is not None, f"Item should not have role=None: {item}"
            if item.get("role") in ["user", "assistant"]:
                assert item.get("content") is not None, f"User/assistant item should not have content=None: {item}"

        # Verify task context is preserved
        thread_content = str(agent_thread.items).lower()
        assert task_id.lower() in thread_content, f"Task {task_id} should be referenced in conversation"

        print("✅ SUCCESS: Conversation content properly preserved in agent-to-agent thread")

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

        # Verify separate threads exist
        user_thread_id = "user->Coordinator"
        agent_thread_id = "Coordinator->Worker"

        thread_manager = coordinator_worker_agency.thread_manager
        assert user_thread_id in thread_manager._threads, f"User thread {user_thread_id} should exist"
        assert agent_thread_id in thread_manager._threads, f"Agent thread {agent_thread_id} should exist"

        user_thread = thread_manager._threads[user_thread_id]
        agent_thread = thread_manager._threads[agent_thread_id]

        # Verify both threads have content
        assert len(user_thread.items) > 0, "User thread should contain conversation items"
        assert len(agent_thread.items) > 0, "Agent-to-agent thread should contain conversation items"

        # Analyze thread contents
        user_content = str(user_thread.items).lower()
        agent_content = str(agent_thread.items).lower()

        print("User thread content check:")
        print(f"  Contains private info: {private_info.lower() in user_content}")
        print(f"  Contains relay info: {relay_info.lower() in user_content}")

        print("Agent thread content check:")
        print(f"  Contains private info: {private_info.lower() in agent_content}")
        print(f"  Contains relay info: {relay_info.lower() in agent_content}")

        # User thread should contain both (user said both to coordinator)
        assert private_info.lower() in user_content, f"User thread should contain private info {private_info}"
        assert relay_info.lower() in user_content, f"User thread should contain relay info {relay_info}"

        # Agent thread should only contain what was relayed to worker
        assert relay_info.lower() in agent_content, f"Agent thread should contain relay info {relay_info}"
        assert private_info.lower() not in agent_content, f"Agent thread should NOT contain private info {private_info}"

        print("✅ SUCCESS: Agent-to-agent thread properly isolated:")
        print(f"  User thread: {len(user_thread.items)} items (has both secrets)")
        print(f"  Agent thread: {len(agent_thread.items)} items (only has relayed info, not private info)")

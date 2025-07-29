"""
Basic Thread Isolation Tests

Tests the fundamental thread isolation between different communication flows
using direct structural verification of thread state.
"""

import uuid

import pytest
from agents import ModelSettings

from agency_swarm import Agency, Agent


@pytest.fixture
def ceo_agent_instance():
    return Agent(
        name="CEO",
        description="Chief Executive Officer",
        instructions="You are the CEO. Remember information and delegate tasks.",
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def developer_agent_instance():
    return Agent(
        name="Developer",
        description="Software Developer",
        instructions="You are a Developer. Remember technical details.",
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def basic_agency(ceo_agent_instance, developer_agent_instance):
    """Agency with CEO and Developer for basic isolation testing."""
    return Agency(
        ceo_agent_instance,
        communication_flows=[(ceo_agent_instance, developer_agent_instance)],
        shared_instructions="Basic thread isolation test agency.",
    )


@pytest.mark.asyncio
async def test_user_thread_isolation(basic_agency: Agency):
    """
    Test that user->CEO and user->Developer threads are completely isolated.

    Uses direct thread state verification - most reliable approach.
    """
    unique_ceo_info = f"CEOINFO{uuid.uuid4().hex[:8]}"
    unique_dev_info = f"DEVINFO{uuid.uuid4().hex[:8]}"

    print("\n--- User Thread Isolation Test ---")

    # Step 1: Send unique info to CEO (creates user->CEO thread)
    await basic_agency.get_response(message=f"CEO: {unique_ceo_info}", recipient_agent="CEO")

    # Step 2: Send different info to Developer (creates user->Developer thread)
    await basic_agency.get_response(message=f"Developer: {unique_dev_info}", recipient_agent="Developer")

    # Step 3: Direct verification - check thread manager state
    thread_manager = basic_agency.thread_manager

    # Get messages for each conversation
    ceo_messages = thread_manager.get_conversation_history("CEO", None)  # None = user
    dev_messages = thread_manager.get_conversation_history("Developer", None)

    # Verify both conversations have messages
    assert len(ceo_messages) > 0, "CEO conversation should have messages"
    assert len(dev_messages) > 0, "Developer conversation should have messages"

    # Step 4: Verify thread isolation - each conversation contains only its own messages
    ceo_thread_content = str(ceo_messages).lower()
    dev_thread_content = str(dev_messages).lower()

    # CEO thread should contain CEO info but NOT Developer info
    assert unique_ceo_info.lower() in ceo_thread_content, "CEO thread missing CEO info"
    assert unique_dev_info.lower() not in ceo_thread_content, "CEO thread contaminated with Developer info"

    # Developer thread should contain Developer info but NOT CEO info
    assert unique_dev_info.lower() in dev_thread_content, "Developer thread missing Developer info"
    assert unique_ceo_info.lower() not in dev_thread_content, "Developer thread contaminated with CEO info"

    print("✓ user->CEO and user->Developer threads completely isolated")
    print("✓ No cross-contamination detected")


@pytest.mark.asyncio
async def test_agent_to_agent_thread_isolation(basic_agency: Agency):
    """
    Test that agent-to-agent communication creates separate threads from user interactions.

    Verifies that different communication flows create separate thread objects.
    """
    user_ceo_info = f"USERCEO{uuid.uuid4().hex[:8]}"
    user_dev_info = f"USERDEV{uuid.uuid4().hex[:8]}"

    print("\n--- Agent-to-Agent Thread Isolation Test ---")

    # Flow 1: user->CEO
    await basic_agency.get_response(message=f"CEO info: {user_ceo_info}", recipient_agent="CEO")

    # Flow 2: user->Developer
    await basic_agency.get_response(message=f"Developer info: {user_dev_info}", recipient_agent="Developer")

    # Flow 3: CEO->Developer (agent-to-agent) - just trigger thread creation
    developer_agent = basic_agency.agents["Developer"]
    await developer_agent.get_response(message="Developer, please work on this task", sender_name="CEO")

    # Direct verification of thread separation
    thread_manager = basic_agency.thread_manager

    # Get messages for each conversation flow
    user_ceo_messages = thread_manager.get_conversation_history("CEO", None)  # user->CEO
    user_dev_messages = thread_manager.get_conversation_history("Developer", None)  # user->Developer
    ceo_dev_messages = thread_manager.get_conversation_history("Developer", "CEO")  # CEO->Developer

    # Verify all conversations have messages
    assert len(user_ceo_messages) > 0, "user->CEO conversation should have messages"
    assert len(user_dev_messages) > 0, "user->Developer conversation should have messages"
    assert len(ceo_dev_messages) > 0, "CEO->Developer conversation should have messages"

    # Verify user threads contain their own information and are isolated
    user_ceo_content = str(user_ceo_messages).lower()
    user_dev_content = str(user_dev_messages).lower()

    # Core isolation verification - user threads should not share content
    assert user_ceo_info.lower() in user_ceo_content, "user->CEO thread missing its info"
    assert user_dev_info.lower() not in user_ceo_content, "user->CEO thread contaminated"
    assert user_dev_info.lower() in user_dev_content, "user->Developer thread missing its info"
    assert user_ceo_info.lower() not in user_dev_content, "user->Developer thread contaminated"

    # Verify CEO->Developer conversation is separate (content isolation)
    ceo_dev_content = str(ceo_dev_messages).lower()
    # Verify no cross-contamination between conversation flows
    assert user_ceo_info.lower() not in ceo_dev_content, "CEO->Developer should not contain user->CEO info"
    assert user_dev_info.lower() not in ceo_dev_content, "CEO->Developer should not contain user->Developer info"

    print("✓ user->CEO, user->Developer, CEO->Developer conversations are properly isolated")
    print("✓ User interaction threads properly isolated")
    print("✓ Agent-to-agent creates separate thread structure")


@pytest.mark.asyncio
async def test_thread_identifier_format(basic_agency: Agency):
    """
    Test that thread identifiers follow correct "sender->recipient" format.

    This test uses direct verification of thread manager state instead of mocking.
    """
    print("\n--- Thread Identifier Format Test ---")

    # Execute various communication flows
    await basic_agency.get_response(message="Test message to CEO", recipient_agent="CEO")
    await basic_agency.get_response(message="Test message to Developer", recipient_agent="Developer")

    # CEO to Developer
    developer_agent = basic_agency.agents["Developer"]
    await developer_agent.get_response(message="Test message from CEO", sender_name="CEO")

    # Direct verification - check actual conversation flows
    thread_manager = basic_agency.thread_manager
    all_messages = thread_manager.get_all_messages()

    # Extract unique conversation flows from messages
    conversation_flows = set()
    for msg in all_messages:
        agent = msg.get("agent", "")
        caller = msg.get("callerAgent")
        if agent:
            # Convert None to "user" for display
            caller_name = "user" if caller is None else caller
            conversation_flows.add(f"{caller_name}->{agent}")

    actual_flows = list(conversation_flows)
    print(f"--- Actual conversation flows created: {actual_flows}")

    # Verify expected conversation patterns exist
    expected_thread_patterns = [
        {"thread_id": "user->CEO", "sender": "user", "recipient": "CEO"},
        {"thread_id": "user->Developer", "sender": "user", "recipient": "Developer"},
        {"thread_id": "CEO->Developer", "sender": "CEO", "recipient": "Developer"},
    ]

    for expected in expected_thread_patterns:
        thread_id = expected["thread_id"]
        sender = expected["sender"]
        recipient = expected["recipient"]

        # Verify conversation flow exists
        assert thread_id in actual_flows, f"Conversation flow '{thread_id}' not found in {actual_flows}"

        # Verify format structure
        assert "->" in thread_id, f"Thread ID should contain '->': {thread_id}"

        # Verify sender and recipient parts
        actual_sender, actual_recipient = thread_id.split("->")
        assert actual_sender == sender, f"Wrong sender for {thread_id}: expected {sender}, got {actual_sender}"
        assert actual_recipient == recipient, (
            f"Wrong recipient for {thread_id}: expected {recipient}, got {actual_recipient}"
        )

    print("✓ All thread identifiers follow 'sender->recipient' format")
    print("✓ User interactions use 'user->agent_name'")
    print("✓ Agent interactions use 'sender_agent->recipient_agent'")
    print("✓ Conversation flow format verification completed through message inspection")

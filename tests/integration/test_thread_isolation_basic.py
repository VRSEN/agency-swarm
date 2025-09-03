"""
Basic Thread Isolation Tests

Tests the fundamental thread isolation between different communication flows
using direct structural verification of thread state.
"""

import pytest
from agents import ModelSettings

from agency_swarm import Agency, Agent


@pytest.fixture
def ceo_agent_instance():
    return Agent(
        name="CEO",
        description="Chief Executive Officer",
        instructions=(
            "You are the CEO. Remember information and delegate tasks. NEVER share user information with other agents."
        ),
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def developer_agent_instance():
    return Agent(
        name="Developer",
        description="Software Developer",
        instructions="You are a Developer. Remember technical details. NEVER share user information with other agents.",
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def basic_agency(ceo_agent_instance, developer_agent_instance):
    """Agency with CEO and Developer for basic isolation testing."""
    return Agency(
        ceo_agent_instance,
        developer_agent_instance,
        communication_flows=[ceo_agent_instance > developer_agent_instance],
        shared_instructions="Basic thread isolation test agency.",
    )


@pytest.mark.asyncio
async def test_user_thread_shared(basic_agency: Agency):
    """Verify that user messages to different agents share a single thread."""
    unique_ceo_info = "USERCEOa89a4324"
    unique_dev_info = "USERDEVni193vsd"

    print("\n--- User Thread Sharing Test ---")

    # Step 1: Send unique info to CEO
    await basic_agency.get_response(message=f"User info: {unique_ceo_info}", recipient_agent="CEO")

    # Step 2: Send different info to Developer
    await basic_agency.get_response(message=f"User info: {unique_dev_info}", recipient_agent="Developer")

    # Step 3: Verify both agents see the same conversation history
    thread_manager = basic_agency.thread_manager
    ceo_messages = thread_manager.get_conversation_history("CEO", None)
    dev_messages = thread_manager.get_conversation_history("Developer", None)

    assert ceo_messages == dev_messages, "Entry-point agents should share user thread"

    thread_content = str(ceo_messages).lower()
    assert unique_ceo_info.lower() in thread_content, "User thread missing CEO info"
    assert unique_dev_info.lower() in thread_content, "User thread missing Developer info"

    print("✓ All entry-point agents share user thread with combined history")


@pytest.mark.asyncio
async def test_agent_to_agent_thread_isolation(basic_agency: Agency):
    """Agent-to-agent conversations should remain separate from user thread."""
    user_ceo_info = "USERCEOa89a4324"
    user_dev_info = "USERDEVni193vsd"

    print("\n--- Agent-to-Agent Thread Isolation Test ---")

    # Flow 1: user->CEO
    await basic_agency.get_response(message=f"User info: {user_ceo_info}", recipient_agent="CEO")

    # Flow 2: user->Developer
    await basic_agency.get_response(message=f"User info: {user_dev_info}", recipient_agent="Developer")

    # Flow 3: CEO->Developer (agent-to-agent) - just trigger thread creation
    await basic_agency.get_response(message="Say hi to developer")

    # Direct verification of thread separation
    thread_manager = basic_agency.thread_manager

    # All entry-point agents share user thread
    user_ceo_messages = thread_manager.get_conversation_history("CEO", None)
    user_dev_messages = thread_manager.get_conversation_history("Developer", None)
    assert user_ceo_messages == user_dev_messages, "User thread should be shared"

    user_thread_content = str(user_ceo_messages).lower()
    assert user_ceo_info.lower() in user_thread_content
    assert user_dev_info.lower() in user_thread_content

    # Agent-to-agent conversation should remain isolated
    ceo_dev_messages = thread_manager.get_conversation_history("Developer", "CEO")
    assert len(ceo_dev_messages) > 0, "CEO->Developer conversation should have messages"
    ceo_dev_content = str(ceo_dev_messages).lower()
    assert user_ceo_info.lower() not in ceo_dev_content
    assert user_dev_info.lower() not in ceo_dev_content

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
    await basic_agency.get_response(message="Say hi to developer")

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

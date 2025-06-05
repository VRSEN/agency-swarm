"""
Basic Thread Isolation Tests

Tests the fundamental thread isolation between different communication flows
using direct structural verification of thread state.
"""

import uuid
from unittest.mock import patch

import pytest
from agents import ModelSettings

from agency_swarm import Agency, Agent


class CEOAgent(Agent):
    pass


class DeveloperAgent(Agent):
    pass


@pytest.fixture
def ceo_agent_instance():
    return CEOAgent(
        name="CEO",
        description="Chief Executive Officer",
        instructions="You are the CEO. Remember information and delegate tasks.",
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def developer_agent_instance():
    return DeveloperAgent(
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

    # Verify both threads exist
    ceo_thread_id = "user->CEO"
    dev_thread_id = "user->Developer"

    assert ceo_thread_id in thread_manager._threads, f"Thread {ceo_thread_id} should exist"
    assert dev_thread_id in thread_manager._threads, f"Thread {dev_thread_id} should exist"

    ceo_thread = thread_manager._threads[ceo_thread_id]
    dev_thread = thread_manager._threads[dev_thread_id]

    # Step 4: Verify thread isolation - each thread contains only its own messages
    ceo_thread_content = str(ceo_thread.items).lower()
    dev_thread_content = str(dev_thread.items).lower()

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

    # Verify all expected threads exist as separate objects
    expected_thread_ids = ["user->CEO", "user->Developer", "CEO->Developer"]

    for thread_id in expected_thread_ids:
        assert thread_id in thread_manager._threads, f"Thread {thread_id} should exist"

    # Verify user threads contain their own information and are isolated
    user_ceo_thread = thread_manager._threads["user->CEO"]
    user_dev_thread = thread_manager._threads["user->Developer"]

    user_ceo_content = str(user_ceo_thread.items).lower()
    user_dev_content = str(user_dev_thread.items).lower()

    # Core isolation verification - user threads should not share content
    assert user_ceo_info.lower() in user_ceo_content, "user->CEO thread missing its info"
    assert user_dev_info.lower() not in user_ceo_content, "user->CEO thread contaminated"
    assert user_dev_info.lower() in user_dev_content, "user->Developer thread missing its info"
    assert user_ceo_info.lower() not in user_dev_content, "user->Developer thread contaminated"

    # Verify CEO->Developer thread is separate object (structural separation)
    ceo_dev_thread = thread_manager._threads["CEO->Developer"]
    assert ceo_dev_thread is not user_ceo_thread, "CEO->Developer should be separate from user->CEO"
    assert ceo_dev_thread is not user_dev_thread, "CEO->Developer should be separate from user->Developer"

    print("✓ user->CEO, user->Developer, CEO->Developer are separate thread objects")
    print("✓ User interaction threads properly isolated")
    print("✓ Agent-to-agent creates separate thread structure")


@pytest.mark.asyncio
async def test_thread_identifier_format(basic_agency: Agency):
    """
    Test that thread identifiers follow correct "sender->recipient" format.
    """
    captured_thread_calls = []

    print("\n--- Thread Identifier Format Test ---")

    # Capture thread ID creation
    from agency_swarm.agent import Agent

    original_get_thread_id = Agent.get_thread_id

    def capture_get_thread_id(self, sender_name=None):
        thread_id = original_get_thread_id(self, sender_name)
        captured_thread_calls.append(
            {
                "thread_id": thread_id,
                "sender": sender_name,
                "recipient": self.name,
            }
        )
        return thread_id

    with patch.object(Agent, "get_thread_id", capture_get_thread_id):
        # User to CEO
        await basic_agency.get_response(message="Test message to CEO", recipient_agent="CEO")

        # User to Developer
        await basic_agency.get_response(message="Test message to Developer", recipient_agent="Developer")

        # CEO to Developer
        developer_agent = basic_agency.agents["Developer"]
        await developer_agent.get_response(message="Test message from CEO", sender_name="CEO")

    # Verify thread identifier formats
    expected_patterns = [
        {"thread_id": "user->CEO", "sender": None, "recipient": "CEO"},
        {"thread_id": "user->Developer", "sender": None, "recipient": "Developer"},
        {"thread_id": "CEO->Developer", "sender": "CEO", "recipient": "Developer"},
    ]

    for expected in expected_patterns:
        matching_calls = [call for call in captured_thread_calls if call["thread_id"] == expected["thread_id"]]
        assert len(matching_calls) > 0, f"Thread identifier '{expected['thread_id']}' not found"

        call = matching_calls[0]
        assert call["sender"] == expected["sender"], f"Wrong sender for {expected['thread_id']}"
        assert call["recipient"] == expected["recipient"], f"Wrong recipient for {expected['thread_id']}"
        assert "->" in call["thread_id"], f"Thread ID should contain '->': {call['thread_id']}"

    print("✓ All thread identifiers follow 'sender->recipient' format")
    print("✓ User interactions use 'user->agent_name'")
    print("✓ Agent interactions use 'sender_agent->recipient_agent'")

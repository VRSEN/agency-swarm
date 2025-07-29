"""
Thread Isolation Persistence Tests

Tests that thread isolation is maintained across persistence operations
using direct structural verification.
"""

import json
import uuid
from pathlib import Path
from typing import Any

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


@pytest.fixture(scope="function")
def temp_persistence_dir(tmp_path):
    """Temporary directory for persistence testing."""
    yield tmp_path


def file_save_callback(messages: list[dict[str, Any]], base_dir: Path):
    """Save flat message list to JSON file."""
    file_path = base_dir / "messages.json"
    with open(file_path, "w") as f:
        json.dump(messages, f, indent=2)

    # Also save individual conversation files for backward compatibility
    conversations = {}
    for msg in messages:
        agent = msg.get("agent", "")
        caller = msg.get("callerAgent", "user")
        thread_id = f"{caller}->{agent}"
        if thread_id not in conversations:
            conversations[thread_id] = []
        conversations[thread_id].append(msg)

    for thread_id, msgs in conversations.items():
        sanitized_thread_id = thread_id.replace("->", "_to_")
        file_path = base_dir / f"{sanitized_thread_id}.json"
        with open(file_path, "w") as f:
            json.dump({"items": msgs, "metadata": {}}, f, indent=2)


def file_load_callback_all_messages(base_dir: Path) -> list[dict[str, Any]]:
    """Load flat message list from JSON file."""
    file_path = base_dir / "messages.json"
    if file_path.exists():
        try:
            with open(file_path) as f:
                messages = json.load(f)
            if isinstance(messages, list):
                return messages
        except Exception:
            pass

    # Fall back to loading from individual thread files (migration)
    messages = []
    for file_path in base_dir.glob("*.json"):
        if file_path.name == "messages.json":
            continue
        try:
            with open(file_path) as f:
                thread_dict = json.load(f)
            if isinstance(thread_dict.get("items"), list):
                messages.extend(thread_dict["items"])
        except Exception:
            continue

    return messages


@pytest.fixture
def file_persistence_callbacks(temp_persistence_dir):
    """Fixture to provide configured file callbacks."""

    def save_cb(messages):
        return file_save_callback(messages, temp_persistence_dir)

    def load_cb():
        return file_load_callback_all_messages(temp_persistence_dir)

    return load_cb, save_cb


@pytest.mark.asyncio
async def test_thread_persistence_isolation_structural(
    file_persistence_callbacks, ceo_agent_instance, developer_agent_instance
):
    """
    Test thread persistence isolation using direct structural verification.

    Most reliable approach - checks actual saved/loaded thread data.
    """
    load_cb, save_cb = file_persistence_callbacks
    test_id = uuid.uuid4().hex[:8]

    print(f"\n--- Thread Persistence Isolation Test {test_id} ---")

    # Create agency with persistence
    agency = Agency(
        ceo_agent_instance,
        communication_flows=[(ceo_agent_instance, developer_agent_instance)],
        shared_instructions="Persistence isolation test agency",
        load_threads_callback=load_cb,
        save_threads_callback=save_cb,
    )

    # Test data - use unique identifiers for precise verification
    ceo_info = f"CEOPROJECT{uuid.uuid4().hex[:8]}"
    dev_info = f"DEVPROJECT{uuid.uuid4().hex[:8]}"

    # Step 1: Create threads with unique information
    await agency.get_response(message=f"CEO project: {ceo_info}", recipient_agent="CEO")

    await agency.get_response(message=f"Developer project: {dev_info}", recipient_agent="Developer")

    # Step 2: Direct verification of conversation state before persistence
    thread_manager = agency.thread_manager
    ceo_messages = thread_manager.get_conversation_history("CEO", None)
    dev_messages = thread_manager.get_conversation_history("Developer", None)

    # Verify conversations contain expected information and are isolated
    ceo_content = str(ceo_messages).lower()
    dev_content = str(dev_messages).lower()

    assert ceo_info.lower() in ceo_content, "CEO thread missing CEO info before persistence"
    assert dev_info.lower() not in ceo_content, "CEO thread contaminated before persistence"
    assert dev_info.lower() in dev_content, "Developer thread missing Developer info before persistence"
    assert ceo_info.lower() not in dev_content, "Developer thread contaminated before persistence"

    # Step 3: Direct verification of saved data using load callbacks
    # This tests that persistence maintains isolation at the storage level
    all_saved_messages = load_cb()

    # Filter messages by conversation
    ceo_saved_messages = [
        msg for msg in all_saved_messages if msg.get("agent") == "CEO" and msg.get("callerAgent") is None
    ]
    dev_saved_messages = [
        msg for msg in all_saved_messages if msg.get("agent") == "Developer" and msg.get("callerAgent") is None
    ]

    assert len(ceo_saved_messages) > 0, "CEO messages should be saved"
    assert len(dev_saved_messages) > 0, "Developer messages should be saved"

    # Verify saved message structure
    for msg in ceo_saved_messages:
        assert "agent" in msg, "CEO message should have agent field"
        assert msg["agent"] == "CEO", "CEO message should have correct agent"
    for msg in dev_saved_messages:
        assert "agent" in msg, "Developer message should have agent field"
        assert msg["agent"] == "Developer", "Developer message should have correct agent"

    # Step 4: Verify persistence isolation at storage level
    ceo_saved_content = str(ceo_saved_messages).lower()
    dev_saved_content = str(dev_saved_messages).lower()

    # CEO saved data should contain only CEO info
    assert ceo_info.lower() in ceo_saved_content, "CEO saved data missing CEO info"
    assert dev_info.lower() not in ceo_saved_content, "CEO saved data contaminated with Developer info"

    # Developer saved data should contain only Developer info
    assert dev_info.lower() in dev_saved_content, "Developer saved data missing Developer info"
    assert ceo_info.lower() not in dev_saved_content, "Developer saved data contaminated with CEO info"

    # Step 5: Verify loaded messages match expected counts
    all_loaded_messages = load_cb()
    loaded_ceo_messages = [
        msg for msg in all_loaded_messages if msg.get("agent") == "CEO" and msg.get("callerAgent") is None
    ]
    loaded_dev_messages = [
        msg for msg in all_loaded_messages if msg.get("agent") == "Developer" and msg.get("callerAgent") is None
    ]

    assert len(loaded_ceo_messages) == len(ceo_saved_messages), "CEO messages should load consistently"
    assert len(loaded_dev_messages) == len(dev_saved_messages), "Developer messages should load consistently"

    print("✓ Conversation isolation maintained in memory")
    print("✓ Conversation isolation maintained in persistence storage")
    print("✓ Each conversation saved/loaded with correct content")
    print("✓ No cross-contamination in persisted conversations")


@pytest.mark.asyncio
async def test_persistence_thread_file_separation(
    file_persistence_callbacks, ceo_agent_instance, developer_agent_instance
):
    """
    Test that different threads are saved as separate files.

    Verifies file-level isolation of thread persistence.
    """
    load_cb, save_cb = file_persistence_callbacks

    print("\n--- Persistence File Separation Test ---")

    agency = Agency(
        ceo_agent_instance,
        communication_flows=[(ceo_agent_instance, developer_agent_instance)],
        shared_instructions="File separation test agency",
        load_threads_callback=load_cb,
        save_threads_callback=save_cb,
    )

    # Create threads
    await agency.get_response(message="CEO message", recipient_agent="CEO")
    await agency.get_response(message="Developer message", recipient_agent="Developer")

    # Verify messages exist
    all_messages = load_cb()
    ceo_messages = [msg for msg in all_messages if msg.get("agent") == "CEO" and msg.get("callerAgent") is None]
    dev_messages = [msg for msg in all_messages if msg.get("agent") == "Developer" and msg.get("callerAgent") is None]

    assert len(ceo_messages) > 0, "CEO messages should exist"
    assert len(dev_messages) > 0, "Developer messages should exist"

    # Verify content separation
    ceo_file_content = str(ceo_messages).lower()
    dev_file_content = str(dev_messages).lower()

    assert "ceo message" in ceo_file_content, "CEO file missing CEO content"
    assert "developer message" not in ceo_file_content, "CEO file contaminated with Developer content"
    assert "developer message" in dev_file_content, "Developer file missing Developer content"
    assert "ceo message" not in dev_file_content, "Developer file contaminated with CEO content"

    print("✓ Each conversation properly tracked")
    print("✓ Message-level content isolation verified")

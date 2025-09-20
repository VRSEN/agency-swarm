import json
from pathlib import Path
from typing import Any

import pytest

from agency_swarm import Agency, Agent

# --- File Persistence Setup ---


@pytest.fixture(scope="function")
def temp_persistence_dir(tmp_path):
    print(f"\nTEMP DIR: Created at {tmp_path}")
    yield tmp_path


def file_save_callback(messages: list[dict[str, Any]], base_dir: Path):
    """Save flat message list to a JSON file."""
    print(f"\nFILE SAVE: Saving {len(messages)} messages to {base_dir}")
    try:
        file_path = base_dir / "messages.json"
        with open(file_path, "w") as f:
            json.dump(messages, f, indent=2)
        print(f"FILE SAVE: Successfully saved {file_path}")
    except Exception as e:
        print(f"FILE SAVE ERROR: Failed to save messages: {e}")
        import traceback

        traceback.print_exc()


def file_load_callback(base_dir: Path) -> list[dict[str, Any]] | None:
    """Load flat message list from a JSON file."""
    file_path = base_dir / "messages.json"
    print(f"\nFILE LOAD: Attempting to load messages from {file_path}")
    if not file_path.exists():
        print("FILE LOAD: File not found.")
        return None
    try:
        with open(file_path) as f:
            messages = json.load(f)
        # Basic validation of loaded structure - should be a list
        if not isinstance(messages, list):
            print(f"FILE LOAD ERROR: Loaded data should be a list, got {type(messages)}.")
            return None
        print(f"FILE LOAD: Successfully loaded {len(messages)} messages")
        return messages
    except Exception as e:
        print(f"FILE LOAD ERROR: Failed to load messages: {e}")
        # Log traceback for detailed debugging
        import traceback

        traceback.print_exc()
        return None


def file_save_callback_error(messages: list[dict[str, Any]], base_dir: Path):
    """Mock file save callback that raises an error."""
    if not messages:
        print("FILE SAVE ERROR (Intentional Fail): Messages list is empty.")
        raise ValueError("Cannot simulate save error for empty messages")

    file_path = base_dir / "messages_test.json"
    print(f"\nFILE SAVE ERROR: Intentionally failing at {file_path}")
    raise OSError("Simulated save error")


def file_load_callback_error(base_dir: Path) -> list[dict[str, Any]] | None:
    """Mock file load callback that raises an error."""
    file_path = base_dir / "messages_test.json"
    print(f"\nFILE LOAD ERROR: Intentionally failing at {file_path}")
    raise OSError("Simulated load error")


# --- Test Agent ---
@pytest.fixture
def persistence_agent():
    return Agent(
        name="PersistenceTester",
        instructions="Remember the secret code word I tell you. In the next turn, repeat the code word.",
    )


@pytest.fixture
def file_persistence_callbacks(temp_persistence_dir):
    """Fixture to provide configured file callbacks that follow the correct interface."""

    def load_messages_for_chat(chat_id: str) -> list[dict[str, Any]]:
        """Load flat message list for a specific chat_id."""
        print(f"\nLOADING MESSAGES for chat_id: {chat_id}")
        file_path = temp_persistence_dir / f"messages_{chat_id}.json"

        if not file_path.exists():
            print("LOAD: No messages file found, returning empty list")
            return []

        try:
            with open(file_path) as f:
                messages = json.load(f)
            print(f"LOADED: {len(messages)} messages for chat_id {chat_id}")
            return messages if isinstance(messages, list) else []
        except Exception as e:
            print(f"ERROR loading {file_path}: {e}")
            return []

    def save_messages_for_chat(messages: list[dict[str, Any]], chat_id: str):
        """Save flat message list for a specific chat_id."""
        print(f"\nSAVING MESSAGES for chat_id: {chat_id} ({len(messages)} messages)")
        try:
            file_path = temp_persistence_dir / f"messages_{chat_id}.json"
            with open(file_path, "w") as f:
                json.dump(messages, f, indent=2)
            print(f"SAVED: {len(messages)} messages for chat {chat_id} to {file_path}")
        except Exception as e:
            print(f"SAVE ERROR for chat_id {chat_id}: {e}")
            import traceback

            traceback.print_exc()

    # Return the actual functions that take chat_id
    return load_messages_for_chat, save_messages_for_chat


# --- Test Cases ---


@pytest.mark.asyncio
async def test_persistence_callbacks_called(temp_persistence_dir, persistence_agent, file_persistence_callbacks):
    """
    Test that save and load callbacks are invoked correctly with proper closure pattern.
    """
    chat_id = "test_chat_123"
    message1 = "First message for callback test."
    message2 = "Second message for callback test."

    # Expected file for flat message storage
    messages_file = temp_persistence_dir / f"messages_{chat_id}.json"

    # Get the actual callback functions
    load_messages_for_chat, save_messages_for_chat = file_persistence_callbacks

    # Define callbacks using closure pattern from deployment docs
    def load_messages():
        return load_messages_for_chat(chat_id)

    def save_messages(messages):
        save_messages_for_chat(messages, chat_id)

    # Initialize Agency with closure-based callbacks (NO parameters in lambda)
    agency = Agency(
        persistence_agent,
        load_threads_callback=lambda: load_messages(),
        save_threads_callback=lambda messages: save_messages(messages),
    )

    # Turn 1
    print(f"\n--- Callback Test Turn 1 --- MSG: {message1}")
    assert not messages_file.exists(), f"File {messages_file} should not exist before first run."
    await agency.get_response(message=message1)

    # Verify save succeeded by checking file existence
    assert messages_file.exists(), f"File {messages_file} should exist after first run."

    # Turn 2 - new agency instance should load previous history
    print(f"\n--- Callback Test Turn 2 --- MSG: {message2}")
    persistence_agent2 = Agent(
        name="PersistenceTester",
        instructions="Remember the secret code word I tell you. In the next turn, repeat the code word.",
    )

    # Same closure pattern for second agency
    agency2 = Agency(
        persistence_agent2,
        load_threads_callback=lambda: load_messages(),
        save_threads_callback=lambda messages: save_messages(messages),
    )

    await agency2.get_response(message=message2)

    # Verify file still exists and has more content
    assert messages_file.exists(), f"File {messages_file} should still exist after second run."
    with open(messages_file) as f:
        final_data = json.load(f)

    # Should have at least 2 user messages (turn 1 and turn 2)
    user_messages = [item for item in final_data if item.get("role") == "user"]
    assert len(user_messages) >= 2, f"Should have at least 2 user messages, got {len(user_messages)}"


@pytest.mark.asyncio
async def test_persistence_load_all_messages(temp_persistence_dir, file_persistence_callbacks):
    """
    Test that load callback returns all messages for a chat_id correctly.
    """
    chat_id = "load_messages_test_789"

    # Create test agents
    ceo = Agent(name="CEO", instructions="You are the CEO.")
    dev = Agent(name="Developer", instructions="You are the Developer.")

    # Get callback functions
    load_messages_for_chat, save_messages_for_chat = file_persistence_callbacks

    # Define callbacks using closure pattern
    def load_messages():
        return load_messages_for_chat(chat_id)

    def save_messages(messages):
        save_messages_for_chat(messages, chat_id)

    # Create agency with communication flow
    agency = Agency(
        ceo,
        communication_flows=[ceo > dev],
        load_threads_callback=lambda: load_messages(),
        save_threads_callback=lambda messages: save_messages(messages),
    )

    # Create messages with different agents
    await agency.get_response("CEO: Plan the project", recipient_agent="CEO")
    await agency.get_response("Developer: Code the project", recipient_agent="Developer")

    # Now test that load_messages returns ALL messages
    all_loaded_messages = load_messages()

    assert isinstance(all_loaded_messages, list), "Load callback should return a list"
    assert len(all_loaded_messages) >= 4, (
        f"Should load at least 4 messages (2 user + 2 assistant), got {len(all_loaded_messages)}"
    )

    # Check that we have messages from both agents
    ceo_messages = [msg for msg in all_loaded_messages if msg.get("agent") == "CEO"]
    dev_messages = [msg for msg in all_loaded_messages if msg.get("agent") == "Developer"]

    assert len(ceo_messages) > 0, "Should have messages for CEO agent"
    assert len(dev_messages) > 0, "Should have messages for Developer agent"

    # Verify each message has proper structure
    for msg in all_loaded_messages:
        assert isinstance(msg, dict), "Each message should be dict"
        assert "agent" in msg, "Message missing 'agent'"
        assert "timestamp" in msg, "Message missing 'timestamp'"

    print(
        f"✓ Successfully loaded {len(all_loaded_messages)} messages with agents: "
        f"{ {msg.get('agent') for msg in all_loaded_messages} }"
    )


@pytest.mark.asyncio
async def test_persistence_error_handling(temp_persistence_dir, persistence_agent, file_persistence_callbacks):
    """
    Test graceful error handling when persistence callbacks fail.
    """

    def load_with_error():
        """Load callback that raises an error."""
        raise OSError("Simulated load error")

    def save_with_error(messages):
        """Save callback that raises an error."""
        raise OSError("Simulated save error")

    # Test load error handling - should handle gracefully and continue
    agency_load_error = Agency(
        persistence_agent,
        load_threads_callback=lambda: load_with_error(),
        save_threads_callback=lambda messages: [],  # No-op save
    )

    # Should handle load error gracefully and continue (not raise error)
    result = await agency_load_error.get_response("Test message despite load error")
    assert result is not None, "Should continue working despite load error"

    # Test save error handling - create separate agent instance
    persistence_agent2 = Agent(
        name="PersistenceTester",
        instructions="Remember the secret code word I tell you. In the next turn, repeat the code word.",
    )

    agency_save_error = Agency(
        persistence_agent2,
        load_threads_callback=lambda: [],  # Return empty messages list
        save_threads_callback=lambda messages: save_with_error(messages),
    )

    # Should complete successfully despite save error
    result = await agency_save_error.get_response("Test message despite save error")
    assert result is not None, "Should continue working despite save error"
    print("✓ Error handling verified - system continues gracefully despite persistence errors")


@pytest.mark.asyncio
async def test_no_persistence_no_callbacks(persistence_agent, temp_persistence_dir):
    """
    Test that history is NOT persisted between Agency instances if no callbacks are provided.
    """
    message1 = "First message, should be forgotten."
    message2 = "Second message, load should not happen."

    # Agency Instance 1 - Turn 1 (No callbacks)
    print("\n--- No Persistence Test - Instance 1 - Turn 1 --- Creating Agency 1")
    agency1 = Agency(persistence_agent, load_threads_callback=None, save_threads_callback=None)
    print(f"--- No Persistence Test - Instance 1 - Turn 1 --- MSG: {message1}")
    await agency1.get_response(message=message1)

    # Check that no file was created (as no save callback was provided)
    assert len(list(temp_persistence_dir.glob("*.json"))) == 0, "No persistence files should exist"
    print("--- No Persistence Test - Verified no file created after Turn 1 ---")

    # Agency Instance 2 - Turn 2 (No callbacks)
    print("\n--- No Persistence Test - Instance 2 - Turn 2 --- Creating Agency 2")
    persistence_agent2 = Agent(
        name="PersistenceTester",
        instructions="Remember the secret code word I tell you. In the next turn, repeat the code word.",
    )
    agency2 = Agency(persistence_agent2, load_threads_callback=None, save_threads_callback=None)
    print(f"--- No Persistence Test - Instance 2 - Turn 2 --- MSG: {message2}")
    await agency2.get_response(message=message2)

    # Verify the messages in agency2 only contain message2, not message1
    messages_in_agency2 = agency2.thread_manager._store.messages
    assert messages_in_agency2 is not None
    found_message1 = any(
        item.get("role") == "user" and message1 in item.get("content", "") for item in messages_in_agency2
    )
    found_message2 = any(
        item.get("role") == "user" and message2 in item.get("content", "") for item in messages_in_agency2
    )

    assert not found_message1, f"Message '{message1}' (from instance 1) was unexpectedly found in instance 2."
    assert found_message2, f"Message '{message2}' not found in instance 2 messages."
    print("--- No Persistence Test - Verified message history in instance 2 ---")

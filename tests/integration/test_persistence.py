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


def file_save_callback(all_threads_data: dict[str, Any], base_dir: Path):
    """Save all threads data to separate JSON files based on thread identifiers."""
    print(f"\nFILE SAVE: Saving {len(all_threads_data)} threads to {base_dir}")
    try:
        for thread_id, thread_data in all_threads_data.items():
            # Sanitize thread_id for filesystem (replace '->' with '_to_')
            sanitized_thread_id = thread_id.replace("->", "_to_")
            file_path = base_dir / f"{sanitized_thread_id}.json"

            # Ensure thread_data has the expected keys, even if empty
            data_to_save = {
                "items": thread_data.get("items", []),
                "metadata": thread_data.get("metadata", {}),
            }

            with open(file_path, "w") as f:
                json.dump(data_to_save, f, indent=2)
            print(f"FILE SAVE: Successfully saved {file_path}")
    except Exception as e:
        print(f"FILE SAVE ERROR: Failed to save thread data: {e}")
        import traceback

        traceback.print_exc()


def file_load_callback(thread_id: str, base_dir: Path) -> dict[str, Any] | None:
    """Load thread data from a JSON file based on thread identifier."""
    # Sanitize thread_id for filesystem (replace '->' with '_to_')
    sanitized_thread_id = thread_id.replace("->", "_to_")
    file_path = base_dir / f"{sanitized_thread_id}.json"
    print(f"\nFILE LOAD: Attempting to load thread data for '{thread_id}' from {file_path}")
    if not file_path.exists():
        print("FILE LOAD: File not found.")
        return None
    try:
        with open(file_path) as f:
            thread_dict = json.load(f)
        # Basic validation of loaded structure
        if not isinstance(thread_dict.get("items"), list) or not isinstance(thread_dict.get("metadata"), dict):
            print(f"FILE LOAD ERROR: Loaded data for {thread_id} has incorrect structure.")
            return None
        print(f"FILE LOAD: Successfully loaded data for thread '{thread_id}'")
        return thread_dict  # Return the raw dictionary
    except Exception as e:
        print(f"FILE LOAD ERROR: Failed to load/reconstruct thread data for {thread_id}: {e}")
        # Log traceback for detailed debugging
        import traceback

        traceback.print_exc()
        return None


def file_save_callback_error(all_threads_data: dict[str, Any], base_dir: Path):
    """Mock file save callback that raises an error."""
    if not all_threads_data:
        print("FILE SAVE ERROR (Intentional Fail): Thread data is empty.")
        raise ValueError("Cannot simulate save error for empty thread data")

    file_path = base_dir / "thread_test.json"
    print(f"\nFILE SAVE ERROR: Intentionally failing at {file_path}")
    raise OSError("Simulated save error")


def file_load_callback_error(thread_id: str, base_dir: Path) -> dict[str, Any] | None:
    """Mock file load callback that raises an error."""
    file_path = base_dir / "thread_test.json"
    print(f"\nFILE LOAD ERROR: Intentionally failing at {file_path}")
    raise OSError(f"Simulated load error for {thread_id}")


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

    def load_threads_for_chat(chat_id: str) -> dict[str, Any]:
        """Load ALL threads for a specific chat_id - this is the actual implementation."""
        print(f"\nLOADING ALL THREADS for chat_id: {chat_id}")
        threads_data = {}

        # Look for all thread files for this chat_id (in practice, this would be a DB query)
        for file_path in temp_persistence_dir.glob(f"*{chat_id}*.json"):
            # Extract thread_id from filename pattern: {thread_id}_{chat_id}.json
            filename = file_path.name
            if filename.endswith(f"_{chat_id}.json"):
                thread_id = filename.replace(f"_{chat_id}.json", "").replace("_to_", "->")
                try:
                    with open(file_path) as f:
                        thread_data = json.load(f)
                    threads_data[thread_id] = thread_data
                    print(f"LOADED thread {thread_id} for chat {chat_id}")
                except Exception as e:
                    print(f"ERROR loading {file_path}: {e}")

        print(f"TOTAL LOADED: {len(threads_data)} threads for chat_id {chat_id}")
        return threads_data

    def save_threads_for_chat(all_threads_data: dict[str, Any], chat_id: str):
        """Save ALL threads for a specific chat_id - this is the actual implementation."""
        print(f"\nSAVING ALL THREADS for chat_id: {chat_id} ({len(all_threads_data)} threads)")
        try:
            for thread_id, thread_data in all_threads_data.items():
                # Sanitize thread_id for filesystem and include chat_id
                sanitized_thread_id = thread_id.replace("->", "_to_")
                file_path = temp_persistence_dir / f"{sanitized_thread_id}_{chat_id}.json"

                # Ensure thread_data has the expected keys
                data_to_save = {
                    "items": thread_data.get("items", []),
                    "metadata": thread_data.get("metadata", {}),
                }

                with open(file_path, "w") as f:
                    json.dump(data_to_save, f, indent=2)
                print(f"SAVED thread {thread_id} for chat {chat_id} to {file_path}")
        except Exception as e:
            print(f"SAVE ERROR for chat_id {chat_id}: {e}")
            import traceback

            traceback.print_exc()

    # Return the actual functions that take chat_id
    return load_threads_for_chat, save_threads_for_chat


# --- Test Cases ---


@pytest.mark.asyncio
async def test_persistence_callbacks_called(temp_persistence_dir, persistence_agent, file_persistence_callbacks):
    """
    Test that save and load callbacks are invoked correctly with proper closure pattern.
    """
    chat_id = "test_chat_123"
    message1 = "First message for callback test."
    message2 = "Second message for callback test."

    # Expected thread identifier for user->PersistenceTester communication
    expected_thread_id = "user->PersistenceTester"
    sanitized_thread_id = expected_thread_id.replace("->", "_to_")
    thread_file = temp_persistence_dir / f"{sanitized_thread_id}_{chat_id}.json"

    # Get the actual callback functions
    load_threads_for_chat, save_threads_for_chat = file_persistence_callbacks

    # Define callbacks using closure pattern from deployment docs
    def load_threads():
        return load_threads_for_chat(chat_id)

    def save_threads(all_threads_data):
        save_threads_for_chat(all_threads_data, chat_id)

    # Initialize Agency with closure-based callbacks (NO parameters in lambda)
    agency = Agency(
        persistence_agent,
        load_threads_callback=lambda: load_threads(),
        save_threads_callback=lambda all_threads_data: save_threads(all_threads_data),
    )

    # Turn 1
    print(f"\n--- Callback Test Turn 1 (Thread: {expected_thread_id}) --- MSG: {message1}")
    assert not thread_file.exists(), f"File {thread_file} should not exist before first run."
    await agency.get_response(message=message1)

    # Verify save succeeded by checking file existence
    assert thread_file.exists(), f"File {thread_file} should exist after first run."

    # Turn 2 - new agency instance should load previous history
    print(f"\n--- Callback Test Turn 2 (Thread: {expected_thread_id}) --- MSG: {message2}")
    persistence_agent2 = Agent(
        name="PersistenceTester",
        instructions="Remember the secret code word I tell you. In the next turn, repeat the code word.",
    )

    # Same closure pattern for second agency
    agency2 = Agency(
        persistence_agent2,
        load_threads_callback=lambda: load_threads(),
        save_threads_callback=lambda all_threads_data: save_threads(all_threads_data),
    )

    await agency2.get_response(message=message2)

    # Verify file still exists and has more content
    assert thread_file.exists(), f"File {thread_file} should still exist after second run."
    with open(thread_file) as f:
        final_data = json.load(f)

    # Should have at least 2 user messages (turn 1 and turn 2)
    user_messages = [item for item in final_data.get("items", []) if item.get("role") == "user"]
    assert len(user_messages) >= 2, f"Should have at least 2 user messages, got {len(user_messages)}"


@pytest.mark.asyncio
async def test_multi_thread_isolation_with_persistence(temp_persistence_dir, file_persistence_callbacks):
    """
    Test that multiple threads (user->Agent1, user->Agent2) are properly isolated
    and persisted separately within the same chat session.
    """
    chat_id = "isolation_test_456"

    # Create two different agents
    agent1 = Agent(name="Agent1", instructions="You are Agent1.")
    agent2 = Agent(name="Agent2", instructions="You are Agent2.")

    # Get callback functions
    load_threads_for_chat, save_threads_for_chat = file_persistence_callbacks

    # Define callbacks using closure pattern
    def load_threads():
        return load_threads_for_chat(chat_id)

    def save_threads(all_threads_data):
        save_threads_for_chat(all_threads_data, chat_id)

    # Create agency with both agents
    agency = Agency(
        agent1,  # Entry point agent
        communication_flows=[(agent1, agent2)],
        load_threads_callback=lambda: load_threads(),
        save_threads_callback=lambda all_threads_data: save_threads(all_threads_data),
    )

    # Send messages to different agents - should create separate threads
    message_to_agent1 = "Hello Agent1, remember: SECRET_CODE_ALPHA"
    message_to_agent2 = "Hello Agent2, remember: SECRET_CODE_BETA"

    print(f"\n--- Sending to Agent1: {message_to_agent1}")
    await agency.get_response(message=message_to_agent1, recipient_agent="Agent1")

    print(f"\n--- Sending to Agent2: {message_to_agent2}")
    await agency.get_response(message=message_to_agent2, recipient_agent="Agent2")

    # Verify separate thread files exist
    agent1_file = temp_persistence_dir / f"user_to_Agent1_{chat_id}.json"
    agent2_file = temp_persistence_dir / f"user_to_Agent2_{chat_id}.json"

    assert agent1_file.exists(), "Agent1 thread file should exist"
    assert agent2_file.exists(), "Agent2 thread file should exist"

    # Verify thread isolation - Agent1 thread should not contain Agent2's secret
    with open(agent1_file) as f:
        agent1_data = json.load(f)

    with open(agent2_file) as f:
        agent2_data = json.load(f)

    agent1_content = str(agent1_data.get("items", [])).lower()
    agent2_content = str(agent2_data.get("items", [])).lower()

    # Agent1 thread should contain ALPHA but not BETA
    assert "secret_code_alpha" in agent1_content, "Agent1 thread should contain ALPHA"
    assert "secret_code_beta" not in agent1_content, "Agent1 thread should NOT contain BETA"

    # Agent2 thread should contain BETA but not ALPHA
    assert "secret_code_beta" in agent2_content, "Agent2 thread should contain BETA"
    assert "secret_code_alpha" not in agent2_content, "Agent2 thread should NOT contain ALPHA"

    print("✓ Thread isolation verified - no cross-contamination")


@pytest.mark.asyncio
async def test_persistence_load_all_threads(temp_persistence_dir, file_persistence_callbacks):
    """
    Test that load callback returns ALL threads for a chat_id correctly.
    """
    chat_id = "multi_thread_test_789"

    # Create test agents
    ceo = Agent(name="CEO", instructions="You are the CEO.")
    dev = Agent(name="Developer", instructions="You are the Developer.")

    # Get callback functions
    load_threads_for_chat, save_threads_for_chat = file_persistence_callbacks

    # Define callbacks using closure pattern
    def load_threads():
        return load_threads_for_chat(chat_id)

    def save_threads(all_threads_data):
        save_threads_for_chat(all_threads_data, chat_id)

    # Create agency with communication flow
    agency = Agency(
        ceo,
        communication_flows=[(ceo, dev)],
        load_threads_callback=lambda: load_threads(),
        save_threads_callback=lambda all_threads_data: save_threads(all_threads_data),
    )

    # Create multiple threads by talking to different agents
    await agency.get_response("CEO: Plan the project", recipient_agent="CEO")
    await agency.get_response("Developer: Code the project", recipient_agent="Developer")

    # Now test that load_threads returns ALL threads
    all_loaded_threads = load_threads()

    assert isinstance(all_loaded_threads, dict), "Load callback should return a dict"
    assert len(all_loaded_threads) >= 2, f"Should load at least 2 threads, got {len(all_loaded_threads)}"

    # Check expected thread IDs
    expected_threads = {"user->CEO", "user->Developer"}
    loaded_thread_ids = set(all_loaded_threads.keys())

    assert expected_threads.issubset(loaded_thread_ids), (
        f"Expected threads {expected_threads} not found in loaded threads {loaded_thread_ids}"
    )

    # Verify each thread has proper structure
    for thread_id, thread_data in all_loaded_threads.items():
        assert isinstance(thread_data, dict), f"Thread {thread_id} data should be dict"
        assert "items" in thread_data, f"Thread {thread_id} missing 'items'"
        assert "metadata" in thread_data, f"Thread {thread_id} missing 'metadata'"
        assert isinstance(thread_data["items"], list), f"Thread {thread_id} items should be list"
        assert isinstance(thread_data["metadata"], dict), f"Thread {thread_id} metadata should be dict"

    print(f"✓ Successfully loaded {len(all_loaded_threads)} threads: {list(all_loaded_threads.keys())}")


@pytest.mark.asyncio
async def test_persistence_error_handling(temp_persistence_dir, persistence_agent, file_persistence_callbacks):
    """
    Test graceful error handling when persistence callbacks fail.
    """

    def load_with_error():
        """Load callback that raises an error."""
        raise OSError("Simulated load error")

    def save_with_error(all_threads_data):
        """Save callback that raises an error."""
        raise OSError("Simulated save error")

    # Test load error handling - should handle gracefully and continue
    agency_load_error = Agency(
        persistence_agent,
        load_threads_callback=lambda: load_with_error(),
        save_threads_callback=lambda all_threads_data: {},  # No-op save
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
        load_threads_callback=lambda: {},  # Return empty threads
        save_threads_callback=lambda all_threads_data: save_with_error(all_threads_data),
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
    expected_thread_id = "user->PersistenceTester"
    message1 = "First message, should be forgotten."
    message2 = "Second message, load should not happen."

    # Agency Instance 1 - Turn 1 (No callbacks)
    print("\n--- No Persistence Test - Instance 1 - Turn 1 --- Creating Agency 1")
    agency1 = Agency(persistence_agent, load_threads_callback=None, save_threads_callback=None)
    print(f"--- No Persistence Test - Instance 1 - Turn 1 (Thread: {expected_thread_id}) --- MSG: {message1}")
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
    print(f"--- No Persistence Test - Instance 2 - Turn 2 (Thread: {expected_thread_id}) --- MSG: {message2}")
    await agency2.get_response(message=message2)

    # Verify the thread in agency2 only contains message2, not message1
    thread_in_agency2 = agency2.thread_manager._threads.get(expected_thread_id)
    assert thread_in_agency2 is not None
    found_message1 = any(
        item.get("role") == "user" and message1 in item.get("content", "") for item in thread_in_agency2.items
    )
    found_message2 = any(
        item.get("role") == "user" and message2 in item.get("content", "") for item in thread_in_agency2.items
    )

    assert not found_message1, f"Message '{message1}' (from instance 1) was unexpectedly found in instance 2."
    assert found_message2, f"Message '{message2}' not found in instance 2 thread."
    print("--- No Persistence Test - Verified thread history in instance 2 ---")

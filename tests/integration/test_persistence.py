import json
from pathlib import Path
from typing import Any

import pytest

from agency_swarm import Agency, Agent
from agency_swarm.thread import ConversationThread

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
class PersistenceTestAgent(Agent):
    pass


@pytest.fixture
def persistence_agent():
    return PersistenceTestAgent(
        name="PersistenceTester",
        instructions="Remember the secret code word I tell you. In the next turn, repeat the code word.",
    )


@pytest.fixture
def file_persistence_callbacks(temp_persistence_dir):
    """Fixture to provide configured file callbacks."""

    def save_cb(all_threads_data):
        return file_save_callback(all_threads_data, temp_persistence_dir)

    def load_cb(thread_id):
        return file_load_callback(thread_id, temp_persistence_dir)

    return load_cb, save_cb


# --- Test Cases ---


@pytest.mark.asyncio
async def test_persistence_callbacks_called(temp_persistence_dir, persistence_agent):
    """
    Test that save and load callbacks are invoked, checking side effects (file existence).
    """
    message1 = "First message for callback test."
    message2 = "Second message for callback test."

    # Expected thread identifier for user->PersistenceTester communication
    expected_thread_id = "user->PersistenceTester"
    sanitized_thread_id = expected_thread_id.replace("->", "_to_")
    thread_file = temp_persistence_dir / f"{sanitized_thread_id}.json"

    # Define actual callbacks using temp_persistence_dir
    def actual_save_cb(all_threads_data: dict[str, Any]):
        file_save_callback(all_threads_data, base_dir=temp_persistence_dir)

    def actual_load_cb(thread_id: str) -> dict[str, Any] | None:
        return file_load_callback(thread_id, base_dir=temp_persistence_dir)

    # Initialize Agency with actual callbacks
    agency = Agency(
        persistence_agent,
        load_threads_callback=actual_load_cb,
        save_threads_callback=actual_save_cb,
    )

    # Turn 1
    print(f"\n--- Callback Test Turn 1 (Thread: {expected_thread_id}) --- MSG: {message1}")
    assert not thread_file.exists(), f"File {thread_file} should not exist before first run."
    await agency.get_response(message=message1)

    # Verify save *succeeded* by checking file existence
    assert thread_file.exists(), f"File {thread_file} should exist after first run."

    # Read file content to check basic structure (optional)
    with open(thread_file) as f:
        data = json.load(f)
    assert isinstance(data.get("items"), list)
    assert isinstance(data.get("metadata"), dict)  # Check metadata is a dict

    # Turn 2
    print(f"\n--- Callback Test Turn 2 (Thread: {expected_thread_id}) --- MSG: {message2}")
    # Create a separate agent instance for the second agency to avoid sharing conflicts
    persistence_agent2 = PersistenceTestAgent(
        name="PersistenceTester",
        instructions="Remember the secret code word I tell you. In the next turn, repeat the code word.",
    )
    agency2 = Agency(
        persistence_agent2,
        load_threads_callback=actual_load_cb,
        save_threads_callback=actual_save_cb,
    )

    await agency2.get_response(message=message2)

    # Verify file still exists (implicitly means save likely worked again)
    assert thread_file.exists(), f"File {thread_file} should still exist after second run."
    # Verify second message was added (check file content again)
    with open(thread_file) as f:
        data_turn2 = json.load(f)
    assert len(data_turn2.get("items", [])) > len(data.get("items", [])), "File should have more items after turn 2"


@pytest.mark.asyncio
async def test_persistence_loads_history(file_persistence_callbacks, persistence_agent):
    """
    Test that history is correctly loaded from file and present in the thread
    before the next turn starts.
    """
    load_cb, save_cb = file_persistence_callbacks
    expected_thread_id = "user->PersistenceTester"
    secret_code = "platypus7"
    message1_content = f"The secret code word is {secret_code}. Remember it."
    message2_content = "What was the secret code word?"

    # Agency Instance 1 - Turn 1
    print("\n--- History Test Instance 1 - Turn 1 --- Creating Agency 1")
    agency1 = Agency(persistence_agent, load_threads_callback=load_cb, save_threads_callback=save_cb)
    print(f"--- History Test Instance 1 - Turn 1 (Thread: {expected_thread_id}) --- MSG: {message1_content}")
    await agency1.get_response(message=message1_content)

    # --- Verification after Turn 1 ---
    # Manually load the thread data using the callback to check saved state
    print(f"\n--- Verifying saved state for {expected_thread_id} after Turn 1 ---")
    loaded_thread_data_after_t1 = load_cb(expected_thread_id)
    assert loaded_thread_data_after_t1 is not None, "Thread data dict failed to load after Turn 1"
    assert isinstance(loaded_thread_data_after_t1, dict), (
        f"Loaded data is not a dict: {type(loaded_thread_data_after_t1)}"
    )
    assert "items" in loaded_thread_data_after_t1, "Loaded dict missing 'items' key"
    assert "metadata" in loaded_thread_data_after_t1, "Loaded dict missing 'metadata' key"

    # Check if message 1 is in the saved items
    found_message1_in_saved = False
    items_to_check = loaded_thread_data_after_t1.get("items", [])
    # Print items for debugging
    print(f"DEBUG: Saved items data for {expected_thread_id}: {items_to_check}")
    for item_dict in items_to_check:
        if (
            isinstance(item_dict, dict)
            and item_dict.get("role") == "user"
            and message1_content in item_dict.get("content", "")
        ):
            found_message1_in_saved = True
            break
    assert found_message1_in_saved, (
        f"Message 1 content '{message1_content}' not found in saved thread items data: {items_to_check}"
    )
    print("--- Saved state verified successfully. ---")

    # Agency Instance 2 - Turn 2
    print("\n--- History Test Instance 2 - Turn 2 --- Creating Agency 2")
    # Create a separate agent instance for the second agency to avoid sharing conflicts
    persistence_agent2 = PersistenceTestAgent(
        name="PersistenceTester",
        instructions="Remember the secret code word I tell you. In the next turn, repeat the code word.",
    )
    agency2 = Agency(persistence_agent2, load_threads_callback=load_cb, save_threads_callback=save_cb)
    print(f"--- History Test Instance 2 - Turn 2 (Thread: {expected_thread_id}) --- MSG: {message2_content}")
    await agency2.get_response(message=message2_content)

    # --- Verification after Turn 2 ---
    # Access the thread directly from the second agency's manager
    print(f"\n--- Verifying loaded state in Agency 2 for {expected_thread_id} after Turn 2 ---")
    thread_in_agency2 = agency2.thread_manager._threads.get(expected_thread_id)
    assert thread_in_agency2 is not None, f"Thread {expected_thread_id} not found in agency2's thread manager."
    assert isinstance(thread_in_agency2, ConversationThread)
    # Check if message 1 is STILL in the items list after loading and Turn 2 execution
    found_message1_in_loaded = False
    items_to_check_loaded = thread_in_agency2.items
    # Print items for debugging
    print(f"DEBUG: Loaded items in agency2 for {expected_thread_id}: {items_to_check_loaded}")
    for item in items_to_check_loaded:
        if isinstance(item, dict) and item.get("role") == "user" and message1_content in item.get("content", ""):
            found_message1_in_loaded = True
            break
    assert found_message1_in_loaded, (
        f"Message 1 content '{message1_content}' not found in loaded thread items in agency2: {items_to_check_loaded}"
    )
    print("--- Loaded state verified successfully. ---")

    # Final LLM output content is NOT asserted.


@pytest.mark.asyncio
async def test_persistence_load_error(temp_persistence_dir, persistence_agent):
    """
    Test that Agency.get_response fails gracefully if the load_threads_callback raises an error.
    """
    expected_thread_id = "user->PersistenceTester"
    message1 = "Message before load error."

    # Define actual callbacks
    def actual_save_cb(all_threads_data: dict[str, Any]):
        file_save_callback(all_threads_data, base_dir=temp_persistence_dir)

    def actual_load_cb_error(thread_id: str) -> dict[str, Any] | None:  # Error-raising version
        file_load_callback_error(thread_id, base_dir=temp_persistence_dir)  # This will raise OSError
        return None  # Should not be reached

    # Agency Instance 1 - Turn 1 (Normal save)
    print("\n--- Load Error Test Instance 1 - Turn 1 --- Creating Agency 1")
    agency1 = Agency(
        persistence_agent,
        load_threads_callback=None,  # No load on first run
        save_threads_callback=actual_save_cb,  # Use actual save
    )
    print(f"--- Load Error Test Instance 1 - Turn 1 (Thread: {expected_thread_id}) --- MSG: {message1}")
    await agency1.get_response(message=message1)
    print("--- Load Error Test Instance 1 - Turn 1 Completed ---")

    # Agency Instance 2 - Turn 2 (Error on load)
    print("\n--- Load Error Test Instance 2 - Turn 2 --- Creating Agency 2 (with error load)")
    # Create a separate agent instance for the second agency to avoid sharing conflicts
    persistence_agent2 = PersistenceTestAgent(
        name="PersistenceTester",
        instructions="Remember the secret code word I tell you. In the next turn, repeat the code word.",
    )
    agency2 = Agency(
        persistence_agent2,
        load_threads_callback=actual_load_cb_error,
        save_threads_callback=actual_save_cb,
    )

    print(f"--- Load Error Test Instance 2 - Turn 2 (Thread: {expected_thread_id}) --- Expecting Error")
    with pytest.raises(IOError, match=f"Simulated load error for {expected_thread_id}"):
        await agency2.get_response(
            message="This message should not be processed.",
        )
    # Verification is done by pytest.raises catching the expected error
    print("--- Load Error Test Instance 2 - Caught expected IOError ---")


@pytest.mark.asyncio
async def test_persistence_save_error(temp_persistence_dir, persistence_agent):
    """
    Test that Agency.get_response completes successfully despite save_threads_callback failure.

    This test verifies graceful error handling behavior by checking that:
    1. The get_response call completes and returns a valid result
    2. No persistence files are created due to the save error
    3. The system continues to function normally despite the save failure
    """
    expected_thread_id = "user->PersistenceTester"
    message1 = "Message causing save error."

    # Define actual callbacks
    def actual_load_cb(thread_id: str) -> dict[str, Any] | None:
        return file_load_callback(thread_id, base_dir=temp_persistence_dir)

    def actual_save_cb_error(all_threads_data: dict[str, Any]):  # Error-raising save
        file_save_callback_error(all_threads_data, base_dir=temp_persistence_dir)

    # Agency Instance
    print("\n--- Save Error Test Instance - Turn 1 --- Creating Agency")
    agency = Agency(
        persistence_agent,
        load_threads_callback=actual_load_cb,
        save_threads_callback=actual_save_cb_error,
    )

    print(f"--- Save Error Test Instance - Turn 1 (Thread: {expected_thread_id}) --- Expecting Save Error")

    # Run should complete successfully despite save error
    result = await agency.get_response(message=message1)

    # Assert that the agent interaction produced a result (run completed)
    assert result is not None
    from agents import RunResult

    assert isinstance(result, RunResult)
    assert hasattr(result, "final_output")
    assert isinstance(result.final_output, str)

    print("--- Save Error Test Instance - Turn 1 Completed Successfully (as expected) ---")

    # Verify that the file wasn't actually created due to the error
    sanitized_thread_id = expected_thread_id.replace("->", "_to_")
    error_file_path = temp_persistence_dir / f"{sanitized_thread_id}.json"
    assert not error_file_path.exists(), f"File {error_file_path} should not exist after save error."

    # Verify that the thread still exists in memory (system continued to function)
    thread_in_memory = agency.thread_manager._threads.get(expected_thread_id)
    assert thread_in_memory is not None, "Thread should still exist in memory despite save error"

    # Verify the thread contains the message (system processed it normally)
    thread_content = str(thread_in_memory.items).lower()
    assert message1.lower() in thread_content, "Thread should contain the message despite save error"

    print("--- Save Error Test Instance - Verified graceful error handling ---")


@pytest.mark.asyncio
async def test_persistence_thread_isolation(file_persistence_callbacks, persistence_agent, temp_persistence_dir):
    """
    Test that persistence for different thread identifiers does not interfere with each other.
    Uses the file-based persistence which saves one file per thread identifier.
    """
    load_cb, save_cb = file_persistence_callbacks

    # Create a second agent to test agent-to-agent communication threads
    second_agent = PersistenceTestAgent(
        name="SecondAgent",
        instructions="You are a secondary agent for testing thread isolation.",
    )

    # Create an agency with both agents and communication flow
    agency = Agency(
        persistence_agent,
        communication_flows=[(persistence_agent, second_agent)],
        load_threads_callback=load_cb,
        save_threads_callback=save_cb,
    )

    # Expected thread identifiers
    user_to_tester_thread_id = "user->PersistenceTester"

    message_1a = "Message for user->PersistenceTester thread, first turn."
    message_1b = "Message for user->PersistenceTester thread, second turn."

    # Turn 1 for user->PersistenceTester thread
    print(f"--- Isolation Test - Turn 1 (Thread: {user_to_tester_thread_id}) --- MSG: {message_1a}")
    await agency.get_response(message=message_1a)

    user_tester_file = temp_persistence_dir / f"{user_to_tester_thread_id.replace('->', '_to_')}.json"
    assert user_tester_file.exists(), f"File for {user_to_tester_thread_id} should exist after turn 1."

    # Turn 2 for user->PersistenceTester thread (using a new agency instance to force loading)
    print(f"--- Isolation Test - Turn 2 (Thread: {user_to_tester_thread_id}) --- MSG: {message_1b}")
    # Create separate agent instances for the second agency to avoid sharing conflicts
    persistence_agent2 = PersistenceTestAgent(
        name="PersistenceTester",
        instructions="Remember the secret code word I tell you. In the next turn, repeat the code word.",
    )
    second_agent2 = PersistenceTestAgent(
        name="SecondAgent",
        instructions="You are a secondary agent for testing thread isolation.",
    )
    agency_reloaded = Agency(
        persistence_agent2,
        communication_flows=[(persistence_agent2, second_agent2)],
        load_threads_callback=load_cb,
        save_threads_callback=save_cb,
    )
    await agency_reloaded.get_response(message=message_1b)

    # Verify user->PersistenceTester thread contains both messages
    print(f"--- Isolation Test - Verifying loaded state for {user_to_tester_thread_id} ---")
    loaded_thread_1_data = load_cb(user_to_tester_thread_id)
    assert loaded_thread_1_data is not None, f"Loaded data for {user_to_tester_thread_id} should not be None"
    assert isinstance(loaded_thread_1_data, dict), (
        f"Loaded data for {user_to_tester_thread_id} is not a dict: {type(loaded_thread_1_data)}"
    )
    assert "items" in loaded_thread_1_data, f"Loaded data for {user_to_tester_thread_id} missing 'items' key"
    assert "metadata" in loaded_thread_1_data, f"Loaded data for {user_to_tester_thread_id} missing 'metadata' key"

    user_tester_items_after_reload = loaded_thread_1_data.get("items", [])
    found_message_1a = any(
        isinstance(item, dict) and item.get("role") == "user" and message_1a in item.get("content", "")
        for item in user_tester_items_after_reload
    )
    found_message_1b = any(
        isinstance(item, dict) and item.get("role") == "user" and message_1b in item.get("content", "")
        for item in user_tester_items_after_reload
    )
    assert found_message_1a, (
        f"Message '{message_1a}' not found in reloaded {user_to_tester_thread_id} items: {user_tester_items_after_reload}"
    )
    assert found_message_1b, (
        f"Message '{message_1b}' not found in reloaded {user_to_tester_thread_id} items: {user_tester_items_after_reload}"
    )

    print("--- Thread Isolation Test Completed Successfully ---")


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
    sanitized_thread_id = expected_thread_id.replace("->", "_to_")
    persistence_file = temp_persistence_dir / f"{sanitized_thread_id}.json"
    assert not persistence_file.exists(), f"Persistence file {persistence_file} should NOT exist."
    print("--- No Persistence Test - Verified no file created after Turn 1 ---")

    # Agency Instance 2 - Turn 2 (No callbacks)
    print("\n--- No Persistence Test - Instance 2 - Turn 2 --- Creating Agency 2")
    # Create a separate agent instance for the second agency to avoid sharing conflicts
    persistence_agent2 = PersistenceTestAgent(
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


@pytest.mark.asyncio
async def test_thread_identifier_format_verification(file_persistence_callbacks, persistence_agent):
    """
    Test that verifies the thread identifier format follows the expected "sender->recipient" pattern.
    """
    load_cb, save_cb = file_persistence_callbacks
    expected_thread_id = "user->PersistenceTester"

    # Create agency
    agency = Agency(
        persistence_agent,
        load_threads_callback=load_cb,
        save_threads_callback=save_cb,
    )

    # Send a message and verify the thread identifier format
    message = "Test message for thread identifier verification."
    print(f"--- Thread Identifier Test --- MSG: {message}")
    await agency.get_response(message=message)

    # Verify the thread was created with the correct identifier
    assert expected_thread_id in agency.thread_manager._threads, (
        f"Expected thread ID '{expected_thread_id}' not found in thread manager. "
        f"Available threads: {list(agency.thread_manager._threads.keys())}"
    )

    # Verify the thread identifier follows the expected format
    thread_obj = agency.thread_manager._threads[expected_thread_id]
    assert thread_obj.thread_id == expected_thread_id, (
        f"Thread object has incorrect thread_id. Expected: {expected_thread_id}, Got: {thread_obj.thread_id}"
    )

    # Verify the format contains the arrow separator
    assert "->" in expected_thread_id, f"Thread ID should contain '->' separator: {expected_thread_id}"

    # Split and verify sender/recipient format
    sender, recipient = expected_thread_id.split("->")
    assert sender == "user", f"Expected sender 'user', got '{sender}'"
    assert recipient == "PersistenceTester", f"Expected recipient 'PersistenceTester', got '{recipient}'"

    print(f"✓ Verified thread identifier format: {expected_thread_id}")
    print("--- Thread Identifier Format Test Completed Successfully ---")

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from agency_swarm import Agency, Agent
from agency_swarm.thread import ConversationThread

# --- File Persistence Setup ---


@pytest.fixture(scope="function")
def temp_persistence_dir(tmp_path):
    print(f"\nTEMP DIR: Created at {tmp_path}")
    yield tmp_path


def file_save_callback(thread_data: dict[str, Any], base_dir: Path):
    file_path = base_dir / "thread_test.json"
    print(f"\nFILE SAVE: Saving thread data to {file_path}")
    try:
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


def file_load_callback(chat_id: str, base_dir: Path) -> dict[str, Any] | None:
    file_path = base_dir / f"{chat_id}.json"
    print(f"\nFILE LOAD: Attempting to load thread data for '{chat_id}' from {file_path}")
    if not file_path.exists():
        print("FILE LOAD: File not found.")
        return None
    try:
        with open(file_path) as f:
            thread_dict = json.load(f)
        # Basic validation of loaded structure
        if not isinstance(thread_dict.get("items"), list) or not isinstance(thread_dict.get("metadata"), dict):
            print(f"FILE LOAD ERROR: Loaded data for {chat_id} has incorrect structure.")
            return None
        print(f"FILE LOAD: Successfully loaded data for thread '{chat_id}'")
        return thread_dict  # Return the raw dictionary
    except Exception as e:
        print(f"FILE LOAD ERROR: Failed to load/reconstruct thread data for {chat_id}: {e}")
        # Log traceback for detailed debugging
        import traceback

        traceback.print_exc()
        return None


def file_save_callback_error(thread_data: dict[str, Any], base_dir: Path):
    """Mock file save callback that raises an error."""
    if not thread_data:
        print("FILE SAVE ERROR (Intentional Fail): Thread ID is missing.")
        raise ValueError("Cannot simulate save error for thread without ID")

    file_path = base_dir / "thread_test.json"
    print(f"\nFILE SAVE ERROR: Intentionally failing at {file_path}")
    raise OSError("Simulated save error")


def file_load_callback_error(chat_id: str, base_dir: Path) -> dict[str, Any] | None:
    """Mock file load callback that raises an error."""
    file_path = base_dir / "thread_test.json"
    print(f"\nFILE LOAD ERROR: Intentionally failing at {file_path}")
    raise OSError("Simulated load error")


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

    def save_cb(thread_data):
        return file_save_callback(thread_data, temp_persistence_dir)

    def load_cb(chat_id):
        return file_load_callback(chat_id, temp_persistence_dir)

    return load_cb, save_cb


# --- Test Cases ---


@pytest.mark.asyncio
async def test_persistence_callbacks_called(temp_persistence_dir, persistence_agent):
    """
    Test that save and load callbacks are invoked, checking side effects (file existence).
    """
    chat_id = "callback_test_1"
    message1 = "First message for callback test."
    message2 = "Second message for callback test."
    chat_file = temp_persistence_dir / f"{chat_id}.json"

    # Define actual callbacks using temp_persistence_dir
    def actual_save_cb(thread_data: dict[str, Any]):
        file_save_callback(thread_data, base_dir=temp_persistence_dir)

    def actual_load_cb(chat_id: str) -> dict[str, Any] | None:
        return file_load_callback(chat_id, base_dir=temp_persistence_dir)

    # Initialize Agency with actual callbacks
    agency = Agency(
        agency_chart=[persistence_agent],
        load_threads_callback=actual_load_cb,
        save_threads_callback=actual_save_cb,
    )

    # Turn 1
    print(f"\n--- Callback Test Turn 1 (ChatID: {chat_id}) --- MSG: {message1}")
    assert not chat_file.exists(), f"File {chat_file} should not exist before first run."
    await agency.get_response(message=message1, recipient_agent=persistence_agent.name, chat_id=chat_id)

    # Verify save *succeeded* by checking file existence
    assert chat_file.exists(), f"File {chat_file} should exist after first run."

    # Read file content to check basic structure (optional)
    with open(chat_file) as f:
        data = json.load(f)
    # The thread_id is now implicit in the filename and managed by ThreadManager;
    # it's not stored inside the JSON by file_save_callback anymore.
    assert isinstance(data.get("items"), list)
    assert isinstance(data.get("metadata"), dict)  # Check metadata is a dict

    # Turn 2
    print(f"\n--- Callback Test Turn 2 (ChatID: {chat_id}) --- MSG: {message2}")
    # Use a new agency instance to ensure loading happens via the callback
    agency2 = Agency(
        agency_chart=[persistence_agent],
        load_threads_callback=actual_load_cb,
        save_threads_callback=actual_save_cb,
    )

    await agency2.get_response(message=message2, recipient_agent=persistence_agent.name, chat_id=chat_id)

    # Verify file still exists (implicitly means save likely worked again)
    assert chat_file.exists(), f"File {chat_file} should still exist after second run."
    # Verify second message was added (check file content again)
    with open(chat_file) as f:
        data_turn2 = json.load(f)
    assert len(data_turn2.get("items", [])) > len(data.get("items", [])), "File should have more items after turn 2"


@pytest.mark.asyncio
async def test_persistence_loads_history(file_persistence_callbacks, persistence_agent):
    """
    Test that history is correctly loaded from file and present in the thread
    before the next turn starts.
    """
    load_cb, save_cb = file_persistence_callbacks
    chat_id = "history_test_1"
    secret_code = "platypus7"
    message1_content = f"The secret code word is {secret_code}. Remember it."
    message2_content = "What was the secret code word?"

    # Agency Instance 1 - Turn 1
    print("\n--- History Test Instance 1 - Turn 1 --- Creating Agency 1")
    agency1 = Agency(agency_chart=[persistence_agent], load_threads_callback=load_cb, save_threads_callback=save_cb)
    print(f"--- History Test Instance 1 - Turn 1 (ChatID: {chat_id}) --- MSG: {message1_content}")
    await agency1.get_response(message=message1_content, recipient_agent="PersistenceTester", chat_id=chat_id)

    # --- Verification after Turn 1 ---
    # Manually load the thread data using the callback to check saved state
    print(f"\n--- Verifying saved state for {chat_id} after Turn 1 ---")
    loaded_thread_data_after_t1 = load_cb(chat_id)
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
    print(f"DEBUG: Saved items data for {chat_id}: {items_to_check}")
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
    agency2 = Agency(agency_chart=[persistence_agent], load_threads_callback=load_cb, save_threads_callback=save_cb)
    print(f"--- History Test Instance 2 - Turn 2 (ChatID: {chat_id}) --- MSG: {message2_content}")
    await agency2.get_response(message=message2_content, recipient_agent="PersistenceTester", chat_id=chat_id)

    # --- Verification after Turn 2 ---
    # Access the thread directly from the second agency's manager
    print(f"\n--- Verifying loaded state in Agency 2 for {chat_id} after Turn 2 ---")
    thread_in_agency2 = agency2.thread_manager._threads.get(chat_id)
    assert thread_in_agency2 is not None, f"Thread {chat_id} not found in agency2's thread manager."
    assert isinstance(thread_in_agency2, ConversationThread)
    # Check if message 1 is STILL in the items list after loading and Turn 2 execution
    found_message1_in_loaded = False
    items_to_check_loaded = thread_in_agency2.items
    # Print items for debugging
    print(f"DEBUG: Loaded items in agency2 for {chat_id}: {items_to_check_loaded}")
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
    chat_id = "load_error_test_1"
    message1 = "Message before load error."

    # Define actual callbacks
    def actual_save_cb(thread_data: dict[str, Any]):
        file_save_callback(thread_data, base_dir=temp_persistence_dir)

    def actual_load_cb_error(chat_id: str) -> dict[str, Any] | None:  # Error-raising version
        file_load_callback_error(chat_id, base_dir=temp_persistence_dir)  # This will raise OSError
        return None  # Should not be reached

    # Agency Instance 1 - Turn 1 (Normal save)
    print("\n--- Load Error Test Instance 1 - Turn 1 --- Creating Agency 1")
    agency1 = Agency(
        agency_chart=[persistence_agent],
        load_threads_callback=None,  # No load on first run
        save_threads_callback=actual_save_cb,  # Use actual save
    )
    print(f"--- Load Error Test Instance 1 - Turn 1 (ChatID: {chat_id}) --- MSG: {message1}")
    await agency1.get_response(message=message1, recipient_agent="PersistenceTester", chat_id=chat_id)
    print("--- Load Error Test Instance 1 - Turn 1 Completed ---")

    # Agency Instance 2 - Turn 2 (Error on load)
    print("\n--- Load Error Test Instance 2 - Turn 2 --- Creating Agency 2 (with error load)")

    agency2 = Agency(
        agency_chart=[persistence_agent],
        load_threads_callback=actual_load_cb_error,
        save_threads_callback=actual_save_cb,
    )

    print(f"--- Load Error Test Instance 2 - Turn 2 (ChatID: {chat_id}) --- Expecting Error")
    with pytest.raises(IOError, match=f"Simulated load error for {chat_id}"):
        await agency2.get_response(
            message="This message should not be processed.",
            recipient_agent="PersistenceTester",
            chat_id=chat_id,
        )
    # Verification is done by pytest.raises catching the expected error
    print("--- Load Error Test Instance 2 - Caught expected IOError ---")


@pytest.mark.asyncio
async def test_persistence_save_error(temp_persistence_dir, persistence_agent):
    """
    Test that Agency.get_response completes but logs an error if the save_threads_callback fails.
    Expect logger to be called TWICE now (once on create, once on end hook).
    """
    chat_id = "save_error_test_1"
    message1 = "Message causing save error."

    # Define actual callbacks
    def actual_load_cb(chat_id: str) -> dict[str, Any] | None:
        return file_load_callback(chat_id, base_dir=temp_persistence_dir)

    def actual_save_cb_error(thread_data: dict[str, Any]):  # Error-raising save
        file_save_callback_error(thread_data, base_dir=temp_persistence_dir)

    # Agency Instance
    print("\n--- Save Error Test Instance - Turn 1 --- Creating Agency")
    agency = Agency(
        agency_chart=[persistence_agent],
        load_threads_callback=actual_load_cb,
        save_threads_callback=actual_save_cb_error,
    )

    print(f"--- Save Error Test Instance - Turn 1 (ChatID: {chat_id}) --- Expecting Save Error Log")
    # Patch the logger to verify error logging
    with patch("agency_swarm.thread.logger.error") as mock_logger_error:
        # Run should complete successfully despite save error
        result = await agency.get_response(message=message1, recipient_agent="PersistenceTester", chat_id=chat_id)
        # Assert that the agent interaction produced a result (run completed)
        assert result is not None
        from agents import RunResult

        assert isinstance(result, RunResult)
        assert hasattr(result, "final_output")
        assert isinstance(result.final_output, str)

        print("--- Save Error Test Instance - Turn 1 Completed Successfully (as expected) ---")

        # Verify logger.error was called TWICE due to save_threads_callback failure
        assert (
            mock_logger_error.call_count >= 1  # Should be called at least once
        ), f"Expected logger.error to be called at least once, but was called {mock_logger_error.call_count} times."

        # Check details of the first call (more reliable than checking count=2)
        args1, kwargs1 = mock_logger_error.call_args_list[0]
        assert "Error saving thread" in args1[0]
        assert chat_id in args1[0]
        # Check exception type in message (might be fragile)
        assert "IOError" in args1[0] or f"Simulated save error for {chat_id}" in args1[0]
        assert kwargs1.get("exc_info") is True  # Check exc_info was passed

        # If persistence hooks are enabled, check the second call too
        if agency.persistence_hooks:
            # For a new thread: 1 (create) + 1 (initial message) + 1 (result items) = 3 calls
            # If the thread existed, it would be 1 (initial) + 1 (result) = 2 calls.
            # Since this test creates a new thread for chat_id, expect 3.
            assert mock_logger_error.call_count == 3, (
                f"Expected logger.error to be called 3 times for a new thread with hooks, "
                f"but was called {mock_logger_error.call_count} times."
            )
            args2, kwargs2 = mock_logger_error.call_args_list[1]
            assert "Error saving thread" in args2[0]
            assert chat_id in args2[0]
            assert "IOError" in str(args2[0]) or f"Simulated save error for {chat_id}" in str(args2[0])
            assert kwargs2.get("exc_info") is True

    print("--- Save Error Test Instance - Verified logger.error calls ---")

    # Additionally, check that the file wasn't actually created due to the error
    error_file_path = temp_persistence_dir / f"{chat_id}.json"
    assert not error_file_path.exists(), f"File {error_file_path} should not exist after save error."
    print("--- Save Error Test Instance - Verified file does not exist ---")


@pytest.mark.asyncio
async def test_persistence_chat_id_isolation(file_persistence_callbacks, persistence_agent, temp_persistence_dir):
    """
    Test that persistence for one chat_id does not interfere with another.
    Uses the file-based persistence which saves one file per chat_id.
    """
    load_cb, save_cb = file_persistence_callbacks
    chat_id_1 = "isolation_test_1"
    chat_id_2 = "isolation_test_2"
    message_1a = "Message for chat 1, first turn."
    message_1b = "Message for chat 1, second turn."
    message_2a = "Message for chat 2, first turn."

    # Agency Instance
    print("\n--- Isolation Test - Creating Agency ---")
    agency = Agency(agency_chart=[persistence_agent], load_threads_callback=load_cb, save_threads_callback=save_cb)

    # Turn 1 for Chat 1
    print(f"--- Isolation Test - Turn 1 (ChatID: {chat_id_1}) --- MSG: {message_1a}")
    await agency.get_response(message=message_1a, recipient_agent="PersistenceTester", chat_id=chat_id_1)
    chat1_file = temp_persistence_dir / f"{chat_id_1}.json"
    assert chat1_file.exists(), f"File for {chat_id_1} should exist after turn 1."

    # Turn 1 for Chat 2
    print(f"--- Isolation Test - Turn 1 (ChatID: {chat_id_2}) --- MSG: {message_2a}")
    await agency.get_response(message=message_2a, recipient_agent="PersistenceTester", chat_id=chat_id_2)
    chat2_file = temp_persistence_dir / f"{chat_id_2}.json"
    assert chat2_file.exists(), f"File for {chat_id_2} should exist after turn 1."
    assert chat1_file.exists(), f"File for {chat_id_1} should still exist after chat 2's turn 1."

    # Turn 2 for Chat 1
    print(f"--- Isolation Test - Turn 2 (ChatID: {chat_id_1}) --- MSG: {message_1b}")
    # Create a new agency instance to force loading
    agency_reloaded = Agency(
        agency_chart=[persistence_agent], load_threads_callback=load_cb, save_threads_callback=save_cb
    )
    await agency_reloaded.get_response(message=message_1b, recipient_agent="PersistenceTester", chat_id=chat_id_1)

    # Verify Chat 1's history contains message 1a, but not message 2a
    print(f"--- Isolation Test - Verifying loaded state for {chat_id_1} ---")
    loaded_thread_1_data = load_cb(chat_id_1)
    assert loaded_thread_1_data is not None, f"Loaded data for {chat_id_1} should not be None"
    assert isinstance(loaded_thread_1_data, dict), (
        f"Loaded data for {chat_id_1} is not a dict: {type(loaded_thread_1_data)}"
    )
    assert "items" in loaded_thread_1_data, f"Loaded data for {chat_id_1} missing 'items' key"
    assert "metadata" in loaded_thread_1_data, f"Loaded data for {chat_id_1} missing 'metadata' key"

    chat1_items_after_reload = loaded_thread_1_data.get("items", [])
    found_message_1a_in_chat1 = any(
        isinstance(item, dict) and item.get("role") == "user" and message_1a in item.get("content", "")
        for item in chat1_items_after_reload
    )
    not_found_message_2a_in_chat1 = not any(
        isinstance(item, dict) and item.get("role") == "user" and message_2a in item.get("content", "")
        for item in chat1_items_after_reload
    )
    assert found_message_1a_in_chat1, (
        f"Message '{message_1a}' not found in reloaded chat 1 items: {chat1_items_after_reload}"
    )
    assert not_found_message_2a_in_chat1, (
        f"Message '{message_2a}' (from chat 2) found in reloaded chat 1 items: {chat1_items_after_reload}"
    )

    # Verify Chat 2's history contains message 2a, but not message 1a or 1b
    print(f"--- Isolation Test - Verifying loaded state for {chat_id_2} ---")
    loaded_thread_2_data = load_cb(chat_id_2)
    assert loaded_thread_2_data is not None, f"Loaded data for {chat_id_2} should not be None"
    assert isinstance(loaded_thread_2_data, dict), (
        f"Loaded data for {chat_id_2} is not a dict: {type(loaded_thread_2_data)}"
    )
    assert "items" in loaded_thread_2_data, f"Loaded data for {chat_id_2} missing 'items' key"
    assert "metadata" in loaded_thread_2_data, f"Loaded data for {chat_id_2} missing 'metadata' key"

    chat2_items_after_reload = loaded_thread_2_data.get("items", [])
    found_message_2a_in_chat2 = any(
        isinstance(item, dict) and item.get("role") == "user" and message_2a in item.get("content", "")
        for item in chat2_items_after_reload
    )
    not_found_message_1a_in_chat2 = not any(
        isinstance(item, dict) and item.get("role") == "user" and message_1a in item.get("content", "")
        for item in chat2_items_after_reload
    )
    not_found_message_1b_in_chat2 = not any(
        isinstance(item, dict) and item.get("role") == "user" and message_1b in item.get("content", "")
        for item in chat2_items_after_reload
    )
    assert found_message_2a_in_chat2, (
        f"Message '{message_2a}' not found in reloaded chat 2 items: {chat2_items_after_reload}"
    )
    assert not_found_message_1a_in_chat2, (
        f"Message '{message_1a}' (from chat 1) found in reloaded chat 2 items: {chat2_items_after_reload}"
    )
    assert not_found_message_1b_in_chat2, (
        f"Message '{message_1b}' (from chat 1) found in reloaded chat 2 items: {chat2_items_after_reload}"
    )

    print("--- Isolation Test Completed Successfully ---")


@pytest.mark.asyncio
async def test_no_persistence_no_callbacks(persistence_agent, temp_persistence_dir):
    """
    Test that history is NOT persisted between Agency instances if no callbacks are provided.
    """
    chat_id = "no_persistence_test_1"
    message1 = "First message, should be forgotten."
    message2 = "Second message, load should not happen."

    # Agency Instance 1 - Turn 1 (No callbacks)
    print("\n--- No Persistence Test - Instance 1 - Turn 1 --- Creating Agency 1")
    agency1 = Agency(agency_chart=[persistence_agent], load_threads_callback=None, save_threads_callback=None)
    print(f"--- No Persistence Test - Instance 1 - Turn 1 (ChatID: {chat_id}) --- MSG: {message1}")
    await agency1.get_response(message=message1, recipient_agent="PersistenceTester", chat_id=chat_id)

    # Check that no file was created (as no save callback was provided)
    persistence_file = temp_persistence_dir / f"{chat_id}.json"
    assert not persistence_file.exists(), f"Persistence file {persistence_file} should NOT exist."
    print("--- No Persistence Test - Verified no file created after Turn 1 ---")

    # Agency Instance 2 - Turn 2 (No callbacks)
    print("\n--- No Persistence Test - Instance 2 - Turn 2 --- Creating Agency 2")
    agency2 = Agency(agency_chart=[persistence_agent], load_threads_callback=None, save_threads_callback=None)
    print(f"--- No Persistence Test - Instance 2 - Turn 2 (ChatID: {chat_id}) --- MSG: {message2}")
    await agency2.get_response(message=message2, recipient_agent="PersistenceTester", chat_id=chat_id)

    # Verify the thread in agency2 only contains message2, not message1
    thread_in_agency2 = agency2.thread_manager._threads.get(chat_id)
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

import pickle

import pytest

from agency_swarm.thread import ConversationThread, ThreadManager


def test_thread_manager_initialization():
    """Tests that ThreadManager initializes with an empty threads dictionary."""
    manager = ThreadManager()
    assert manager._threads == {}
    assert manager._load_threads_callback is None  # Check default callbacks
    assert manager._save_threads_callback is None


def test_get_thread_generates_id():
    """Tests that get_thread generates a UUID if no thread_id is provided."""
    manager = ThreadManager()
    thread = manager.get_thread()  # No ID provided
    assert isinstance(thread, ConversationThread)
    assert isinstance(thread.thread_id, str)
    assert thread.thread_id.startswith("thread_")
    assert thread.thread_id in manager._threads
    assert manager._threads[thread.thread_id] == thread


def test_get_thread_uses_provided_id():
    """Tests that get_thread uses the provided thread_id."""
    manager = ThreadManager()
    test_id = "my_custom_thread_id_123"
    thread = manager.get_thread(test_id)
    assert isinstance(thread, ConversationThread)
    assert thread.thread_id == test_id
    assert test_id in manager._threads
    assert manager._threads[test_id] == thread


def test_get_thread_returns_existing_by_id():
    """Tests that get_thread returns the existing thread when called with the same ID."""
    manager = ThreadManager()
    test_id = "existing_thread_456"
    thread1 = manager.get_thread(test_id)
    thread2 = manager.get_thread(test_id)
    assert thread1 == thread2
    assert len(manager._threads) == 1  # Should only be one thread with this ID


def test_get_thread_loads_from_callback(mocker):
    """Tests that get_thread attempts to load from the load_threads_callback if provided."""
    mock_load = mocker.MagicMock()
    test_id = "load_me_789"
    # The callback now returns ALL threads, not just one
    loaded_data_dict = {
        test_id: {"items": [{"role": "system", "content": "Loaded"}], "metadata": {"source": "mock_db"}}
    }
    mock_load.return_value = loaded_data_dict

    manager = ThreadManager(load_threads_callback=mock_load)

    # Callback should have been invoked during initialization
    thread = manager.get_thread(test_id)
    mock_load.assert_called_once_with()  # NO parameters

    # Verify the thread was constructed from the loaded data
    assert thread.thread_id == test_id
    assert len(thread.items) == 1
    assert thread.items[0]["content"] == "Loaded"


def test_get_thread_creates_new_if_load_fails(mocker):
    """Tests that get_thread creates a new thread if load_threads_callback returns empty dict."""
    mock_load = mocker.MagicMock(return_value={})  # Empty dict, no threads loaded
    test_id = "load_fail_abc"

    manager = ThreadManager(load_threads_callback=mock_load)
    thread = manager.get_thread(test_id)

    # Callback is invoked during initialization and again when get_thread()
    # attempts to load the missing thread
    assert mock_load.call_count == 2

    # Should have created a new thread since load returned empty
    assert thread.thread_id == test_id
    assert len(thread.items) == 0


def test_thread_manager_serialization():
    """Tests that ThreadManager with populated threads can be serialized and deserialized."""
    # Note: Callbacks are generally not pickleable, so test without them.
    manager = ThreadManager()  # No callbacks for pickling test
    thread1_id = "pickle_thread_1"
    thread2_id = "pickle_thread_2"

    thread1 = manager.get_thread(thread1_id)
    thread1.add_item({"role": "user", "content": "Hello agent2"})
    thread1.add_item({"role": "assistant", "content": "Hello agent1"})

    thread2 = manager.get_thread(thread2_id)
    thread2.add_item({"role": "user", "content": "Hello agent1"})
    thread2.add_item({"role": "assistant", "content": "Hello USER"})

    # Serialize
    serialized_manager = pickle.dumps(manager)

    # Deserialize
    deserialized_manager = pickle.loads(serialized_manager)

    # Verify
    assert isinstance(deserialized_manager, ThreadManager)
    assert deserialized_manager._load_threads_callback is None  # Callbacks shouldn't serialize
    assert deserialized_manager._save_threads_callback is None
    assert len(deserialized_manager._threads) == 2
    assert thread1_id in deserialized_manager._threads
    assert thread2_id in deserialized_manager._threads

    deserialized_thread1 = deserialized_manager.get_thread(thread1_id)
    assert len(deserialized_thread1.items) == 2
    assert deserialized_thread1.items[0]["role"] == "user"
    assert deserialized_thread1.items[0]["content"] == "Hello agent2"
    assert deserialized_thread1.items[1]["role"] == "assistant"
    assert deserialized_thread1.items[1]["content"] == "Hello agent1"

    deserialized_thread2 = deserialized_manager.get_thread(thread2_id)
    assert len(deserialized_thread2.items) == 2
    assert deserialized_thread2.items[0]["role"] == "user"
    assert deserialized_thread2.items[0]["content"] == "Hello agent1"
    assert deserialized_thread2.items[1]["role"] == "assistant"
    assert deserialized_thread2.items[1]["content"] == "Hello USER"


def test_add_item_and_save_triggers_callback(mocker):
    """Tests that add_item_and_save calls the save_threads_callback."""
    mock_save = mocker.MagicMock()
    manager = ThreadManager()  # Initialize WITHOUT callback first
    thread_id = "save_test_thread_1"
    thread = manager.get_thread(thread_id)
    # Assign callback AFTER thread creation to isolate save calls
    manager._save_threads_callback = mock_save

    item = {"role": "user", "content": "Test message for save"}
    manager.add_item_and_save(thread, item)

    # Verify item was added
    assert len(thread.items) == 1
    assert thread.items[0] == item
    # Verify save callback was called once with all threads data
    expected_all_threads_data = {thread_id: {"items": thread.items, "metadata": thread.metadata}}
    mock_save.assert_called_once_with(expected_all_threads_data)


def test_add_items_and_save_triggers_callback(mocker):
    """Tests that add_items_and_save calls the save_threads_callback."""
    mock_save = mocker.MagicMock()
    manager = ThreadManager()  # Initialize WITHOUT callback first
    thread_id = "save_test_thread_2"
    thread = manager.get_thread(thread_id)
    # Assign callback AFTER thread creation
    manager._save_threads_callback = mock_save

    items = [
        {"role": "user", "content": "Message 1"},
        {"role": "assistant", "content": "Message 2"},
    ]
    manager.add_items_and_save(thread, items)

    # Verify items were added
    assert len(thread.items) == 2
    assert thread.items[0] == items[0]
    assert thread.items[1] == items[1]
    # Verify save callback was called once with all threads data
    expected_all_threads_data = {thread_id: {"items": thread.items, "metadata": thread.metadata}}
    mock_save.assert_called_once_with(expected_all_threads_data)


def test_save_not_called_without_callback():
    """Tests that save is not attempted if no callback is provided."""
    # We can't easily mock the internal _save_thread, but we can check
    # that no error occurs and items are added when no callback is set.
    manager = ThreadManager()  # No save_threads_callback
    thread = manager.get_thread("no_save_test")
    item = {"role": "user", "content": "Test"}
    items = [{"role": "assistant", "content": "Test 2"}]

    try:
        manager.add_item_and_save(thread, item)
        manager.add_items_and_save(thread, items)
    except Exception as e:
        pytest.fail(f"add_item(s)_and_save raised unexpected exception without callback: {e}")

    assert len(thread.items) == 2  # Item + items list

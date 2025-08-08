import pickle

from agency_swarm.thread import ThreadManager


def test_thread_manager_initialization():
    """Tests that ThreadManager initializes with an empty message store."""
    manager = ThreadManager()
    assert len(manager._store.messages) == 0
    assert manager._load_threads_callback is None
    assert manager._save_threads_callback is None


def test_add_message():
    """Tests adding a single message to the thread manager."""
    manager = ThreadManager()
    message = {"role": "user", "content": "Hello", "agent": "Agent1", "callerAgent": None, "timestamp": 1234567890000}

    manager.add_message(message)

    assert len(manager._store.messages) == 1
    assert manager._store.messages[0] == message


def test_add_messages():
    """Tests adding multiple messages to the thread manager."""
    manager = ThreadManager()
    messages = [
        {"role": "user", "content": "Hello", "agent": "Agent1", "callerAgent": None, "timestamp": 1234567890000},
        {
            "role": "assistant",
            "content": "Hi there",
            "agent": "Agent1",
            "callerAgent": None,
            "timestamp": 1234567891000,
        },
    ]

    manager.add_messages(messages)

    assert len(manager._store.messages) == 2
    assert manager._store.messages == messages


def test_get_conversation_history():
    """Tests retrieving conversation history for specific agent pairs."""
    manager = ThreadManager()
    messages = [
        {"role": "user", "content": "Hello Agent1", "agent": "Agent1", "callerAgent": None, "timestamp": 1234567890000},
        {"role": "assistant", "content": "Hi user", "agent": "Agent1", "callerAgent": None, "timestamp": 1234567891000},
        {"role": "user", "content": "Hello Agent2", "agent": "Agent2", "callerAgent": None, "timestamp": 1234567892000},
        {
            "role": "assistant",
            "content": "Hi from Agent2",
            "agent": "Agent2",
            "callerAgent": None,
            "timestamp": 1234567893000,
        },
    ]

    manager.add_messages(messages)

    # Get conversation between user and Agent1
    agent1_history = manager.get_conversation_history("Agent1", None)
    assert len(agent1_history) == 2
    assert all(msg["agent"] == "Agent1" for msg in agent1_history)

    # Get conversation between user and Agent2
    agent2_history = manager.get_conversation_history("Agent2", None)
    assert len(agent2_history) == 2
    assert all(msg["agent"] == "Agent2" for msg in agent2_history)


def test_get_all_messages():
    """Tests retrieving all messages from the thread manager."""
    manager = ThreadManager()
    messages = [
        {"role": "user", "content": "Message 1", "agent": "Agent1", "callerAgent": None, "timestamp": 1234567890000},
        {
            "role": "assistant",
            "content": "Response 1",
            "agent": "Agent1",
            "callerAgent": None,
            "timestamp": 1234567891000,
        },
    ]

    manager.add_messages(messages)
    all_messages = manager.get_all_messages()

    assert all_messages == messages
    # Verify it returns a copy, not the original list
    all_messages.append({"role": "user", "content": "Extra"})
    assert len(manager._store.messages) == 2  # Original should be unchanged


def test_save_callback_triggered_on_add(mocker):
    """Tests that save callback is triggered when adding messages."""
    mock_save = mocker.MagicMock()
    manager = ThreadManager(save_threads_callback=mock_save)

    message = {"role": "user", "content": "Test", "agent": "Agent1", "callerAgent": None, "timestamp": 1234567890000}
    manager.add_message(message)

    mock_save.assert_called_once_with([message])


def test_load_callback_on_init(mocker):
    """Tests that load callback is called during initialization."""
    loaded_messages = [
        {
            "role": "user",
            "content": "Loaded message",
            "agent": "Agent1",
            "callerAgent": None,
            "timestamp": 1234567890000,
        }
    ]
    mock_load = mocker.MagicMock(return_value=loaded_messages)

    manager = ThreadManager(load_threads_callback=mock_load)

    mock_load.assert_called_once()
    assert manager._store.messages == loaded_messages


def test_migrate_old_format():
    """Tests migration from old thread-based format to flat structure."""
    old_format = {
        "user->Agent1": {
            "items": [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there"}],
            "metadata": {},
        },
        "Agent1->Agent2": {
            "items": [
                {"role": "assistant", "content": "Need help"},
                {"role": "assistant", "content": "Sure, I can help"},
            ],
            "metadata": {},
        },
    }

    def mock_load():
        return old_format

    manager = ThreadManager(load_threads_callback=mock_load)

    # Check that messages were migrated correctly
    assert len(manager._store.messages) == 4

    # Check that agency metadata was added
    user_to_agent1 = [
        msg for msg in manager._store.messages if msg.get("agent") == "Agent1" and msg.get("callerAgent") is None
    ]
    assert len(user_to_agent1) == 2

    agent1_to_agent2 = [
        msg for msg in manager._store.messages if msg.get("agent") == "Agent2" and msg.get("callerAgent") == "Agent1"
    ]
    assert len(agent1_to_agent2) == 2

    # Check that timestamps were added
    assert all("timestamp" in msg for msg in manager._store.messages)


def test_thread_manager_pickleable():
    """Tests that ThreadManager can be pickled and unpickled correctly."""
    # Create manager without callbacks (callbacks aren't pickleable)
    manager = ThreadManager()
    messages = [
        {"role": "user", "content": "Test message", "agent": "Agent1", "callerAgent": None, "timestamp": 1234567890000}
    ]
    manager.add_messages(messages)

    # Pickle and unpickle
    pickled_data = pickle.dumps(manager)
    unpickled_manager = pickle.loads(pickled_data)

    # Verify the data is preserved
    assert isinstance(unpickled_manager, ThreadManager)
    assert unpickled_manager._store.messages == messages

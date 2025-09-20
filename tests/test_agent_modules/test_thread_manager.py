import pickle

import pytest

from agency_swarm.utils.thread import ThreadManager


def test_thread_manager_initialization():
    """Tests that ThreadManager initializes with an empty message store."""
    manager = ThreadManager()
    assert len(manager._store.messages) == 0
    assert manager._load_threads_callback is None
    assert manager._save_threads_callback is None


@pytest.mark.parametrize(
    "method,messages",
    [
        (
            "add_message",
            [
                {
                    "role": "user",
                    "content": "Hello",
                    "agent": "Agent1",
                    "callerAgent": None,
                    "timestamp": 1234567890000,
                }
            ],
        ),
        (
            "add_messages",
            [
                {
                    "role": "user",
                    "content": "Hello",
                    "agent": "Agent1",
                    "callerAgent": None,
                    "timestamp": 1234567890000,
                },
                {
                    "role": "assistant",
                    "content": "Hi there",
                    "agent": "Agent1",
                    "callerAgent": None,
                    "timestamp": 1234567891000,
                },
            ],
        ),
    ],
)
def test_add_messages(method: str, messages: list[dict]):
    """Tests adding messages through both single and batch methods."""
    manager = ThreadManager()
    target = messages[0] if method == "add_message" else messages
    getattr(manager, method)(target)

    assert len(manager._store.messages) == len(messages)
    assert manager._store.messages == messages


def test_user_thread_shared_across_agents():
    """Tests that all entry-point agents share the same user thread."""
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

    # Both agents should see the same combined conversation history
    agent1_history = manager.get_conversation_history("Agent1", None)
    agent2_history = manager.get_conversation_history("Agent2", None)

    assert agent1_history == messages
    assert agent2_history == messages
    assert agent1_history == agent2_history


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


def test_replace_messages_skips_save_callback():
    captured: list[list[dict[str, object]]] = []
    manager = ThreadManager(save_threads_callback=lambda msgs: captured.append(list(msgs)))

    manager.add_message({"role": "user", "content": "seed"})
    captured.clear()

    manager.replace_messages([{"role": "assistant", "content": "new"}])

    assert captured == []
    assert [msg["content"] for msg in manager.get_all_messages()] == ["new"]

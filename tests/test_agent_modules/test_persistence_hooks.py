from unittest.mock import MagicMock

import pytest
from agents import RunResult

from agency_swarm import MasterContext, PersistenceHooks, RunContextWrapper, ThreadManager


@pytest.fixture
def mock_load_callback():
    return MagicMock()


@pytest.fixture
def mock_save_callback():
    return MagicMock()


@pytest.fixture
def mock_thread_manager():
    # Mock ThreadManager with the new flat structure
    manager = MagicMock(spec=ThreadManager)
    manager._store = MagicMock()
    manager._store.messages = []
    manager.get_all_messages = MagicMock(return_value=[])
    return manager


@pytest.fixture
def mock_master_context(mock_thread_manager):
    # Mock MasterContext object required by PersistenceHooks
    context = MagicMock(spec=MasterContext)
    context.thread_manager = mock_thread_manager
    context.agents = {}  # Add mock agents if needed by specific tests
    return context


@pytest.fixture
def mock_run_context_wrapper(mock_master_context):
    # Mock RunContextWrapper
    wrapper = MagicMock(spec=RunContextWrapper)
    wrapper.context = mock_master_context
    return wrapper


@pytest.fixture
def mock_run_result():
    # Mock RunResult needed for on_run_end
    result = MagicMock(spec=RunResult)
    result.final_output = "mock output"
    return result


class TestPersistenceHooksUnit:
    @pytest.mark.asyncio
    async def test_on_run_start_success(
        self,
        mock_load_callback,
        mock_save_callback,
        mock_thread_manager,
        mock_run_context_wrapper,
    ):
        """Test PersistenceHooks.on_run_start - messages are loaded by ThreadManager during init."""
        # Arrange
        # With the new structure, loading happens in ThreadManager.__init__
        # PersistenceHooks.on_run_start just logs that loading already occurred

        hooks = PersistenceHooks(load_threads_callback=mock_load_callback, save_threads_callback=mock_save_callback)

        # Act
        hooks.on_run_start(context=mock_run_context_wrapper.context)

        # Assert
        # The hook itself doesn't call load_callback anymore (ThreadManager does during init)
        mock_load_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_run_end_success(
        self,
        mock_load_callback,
        mock_save_callback,
        mock_thread_manager,
        mock_run_context_wrapper,
        mock_run_result,
    ):
        """Test PersistenceHooks.on_run_end successfully calls save_threads_callback with flat message list."""
        # Arrange
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
        mock_thread_manager.get_all_messages.return_value = messages

        hooks = PersistenceHooks(load_threads_callback=mock_load_callback, save_threads_callback=mock_save_callback)

        # Act
        hooks.on_run_end(context=mock_run_context_wrapper.context, result=mock_run_result)

        # Assert
        # Verify save_threads_callback was called with flat message list
        mock_save_callback.assert_called_once_with(messages)

    @pytest.mark.asyncio
    async def test_on_run_end_save_error(
        self,
        mock_load_callback,
        mock_save_callback,
        mock_thread_manager,
        mock_run_context_wrapper,
        mock_run_result,
    ):
        """Test PersistenceHooks.on_run_end when save_threads_callback raises an error."""
        # Arrange
        messages = [
            {
                "role": "user",
                "content": "Test message",
                "agent": "Agent1",
                "callerAgent": None,
                "timestamp": 1234567890000,
            }
        ]
        mock_thread_manager.get_all_messages.return_value = messages

        save_error = OSError("Simulated save error")
        mock_save_callback.side_effect = save_error

        hooks = PersistenceHooks(load_threads_callback=mock_load_callback, save_threads_callback=mock_save_callback)

        # Act & Assert
        # Verify the hook runs without raising the exception itself (it should catch it)
        try:
            hooks.on_run_end(context=mock_run_context_wrapper.context, result=mock_run_result)
        except Exception as e:
            pytest.fail(f"PersistenceHooks.on_run_end raised an unexpected exception: {e}")

        # Verify save_threads_callback was called with flat message list
        mock_save_callback.assert_called_once_with(messages)

    def test_persistence_hooks_init_validation(self, mock_load_callback, mock_save_callback):
        """Test PersistenceHooks initialization validates callbacks are callable."""
        # Valid initialization
        hooks = PersistenceHooks(load_threads_callback=mock_load_callback, save_threads_callback=mock_save_callback)
        assert hooks._load_threads_callback == mock_load_callback
        assert hooks._save_threads_callback == mock_save_callback

        # Invalid initialization - not callable
        with pytest.raises(TypeError, match="load_threads_callback and save_threads_callback must be callable"):
            PersistenceHooks(load_threads_callback="not_callable", save_threads_callback=mock_save_callback)

        with pytest.raises(TypeError, match="load_threads_callback and save_threads_callback must be callable"):
            PersistenceHooks(load_threads_callback=mock_load_callback, save_threads_callback="not_callable")

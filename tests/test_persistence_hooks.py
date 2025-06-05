from unittest.mock import MagicMock

import pytest
from agents import RunContextWrapper, RunResult

from agency_swarm.context import MasterContext
from agency_swarm.hooks import PersistenceHooks
from agency_swarm.thread import ConversationThread, ThreadManager


@pytest.fixture
def mock_load_callback():
    return MagicMock()


@pytest.fixture
def mock_save_callback():
    return MagicMock()


@pytest.fixture
def mock_thread_manager():
    # Simple mock, might need more sophisticated one depending on tests
    manager = MagicMock(spec=ThreadManager)
    manager._threads = {}
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
    # wrapper.hooks can be set if needed
    # wrapper.agent can be set if needed
    return wrapper


@pytest.fixture
def mock_run_result():
    # Mock RunResult needed for on_run_end
    result = MagicMock(spec=RunResult)
    result.final_output = "Test output"
    # Add other attributes if needed by hooks
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
        """Test PersistenceHooks.on_run_start successfully loads thread data."""
        # Arrange
        # Simulate load_callback returning serialized thread data (not ConversationThread objects)
        thread_id_1 = "user->TestAgent"
        thread_id_2 = "user->OtherAgent"
        loaded_threads_data = {
            thread_id_1: {"items": [{"role": "user", "content": "loaded1"}], "metadata": {}},
            thread_id_2: {"items": [{"role": "user", "content": "loaded2"}], "metadata": {}},
        }
        mock_load_callback.return_value = loaded_threads_data  # Simulate successful load returning serialized data

        hooks = PersistenceHooks(load_threads_callback=mock_load_callback, save_threads_callback=mock_save_callback)

        # Act
        # Call on_run_start only with context (it's synchronous)
        hooks.on_run_start(context=mock_run_context_wrapper.context)

        # Assert
        mock_load_callback.assert_called_once_with()  # Called without arguments
        # Verify thread_manager._threads was populated with ConversationThread objects
        assert len(mock_thread_manager._threads) == 2
        assert thread_id_1 in mock_thread_manager._threads
        assert thread_id_2 in mock_thread_manager._threads
        # Verify the threads were reconstructed correctly
        thread_1 = mock_thread_manager._threads[thread_id_1]
        thread_2 = mock_thread_manager._threads[thread_id_2]
        assert thread_1.thread_id == thread_id_1
        assert thread_1.items == [{"role": "user", "content": "loaded1"}]
        assert thread_2.thread_id == thread_id_2
        assert thread_2.items == [{"role": "user", "content": "loaded2"}]

    @pytest.mark.asyncio
    async def test_on_run_start_load_none(
        self,
        mock_load_callback,
        mock_save_callback,
        mock_thread_manager,
        mock_run_context_wrapper,
    ):
        """Test PersistenceHooks.on_run_start when load_threads_callback returns None."""
        # Arrange
        mock_load_callback.return_value = None  # Simulate load returning None
        initial_threads = mock_thread_manager._threads.copy()

        hooks = PersistenceHooks(load_threads_callback=mock_load_callback, save_threads_callback=mock_save_callback)

        # Act
        hooks.on_run_start(context=mock_run_context_wrapper.context)

        # Assert
        mock_load_callback.assert_called_once_with()
        # Verify thread_manager._threads remains unchanged
        assert mock_thread_manager._threads == initial_threads

    @pytest.mark.asyncio
    async def test_on_run_start_load_error(
        self,
        mock_load_callback,
        mock_save_callback,
        mock_thread_manager,
        mock_run_context_wrapper,
    ):
        """Test PersistenceHooks.on_run_start when load_threads_callback raises an error."""
        # Arrange
        load_error = OSError("Simulated load error")
        mock_load_callback.side_effect = load_error  # Simulate load raising error
        initial_threads = mock_thread_manager._threads.copy()

        hooks = PersistenceHooks(load_threads_callback=mock_load_callback, save_threads_callback=mock_save_callback)

        # Act & Assert
        # Verify the hook runs without raising the exception itself (it should catch it)
        try:
            hooks.on_run_start(context=mock_run_context_wrapper.context)
        except Exception as e:
            pytest.fail(f"PersistenceHooks.on_run_start raised an unexpected exception: {e}")

        mock_load_callback.assert_called_once_with()
        # Verify thread_manager._threads remains unchanged
        assert mock_thread_manager._threads == initial_threads
        # Optional: Could capture logs to verify the error was logged, but keeping it simple for now.

    @pytest.mark.asyncio
    async def test_on_run_end_success(
        self,
        mock_load_callback,
        mock_save_callback,
        mock_thread_manager,
        mock_run_context_wrapper,
        mock_run_result,  # Add mock_run_result fixture
    ):
        """Test PersistenceHooks.on_run_end successfully calls save_threads_callback."""
        # Arrange
        thread_id_1 = "user->TestAgent"
        # Pre-populate the mock thread manager with some ConversationThread data
        thread_obj = ConversationThread(thread_id=thread_id_1, items=[{"role": "user", "content": "to_save"}])
        mock_thread_manager._threads = {thread_id_1: thread_obj}

        hooks = PersistenceHooks(load_threads_callback=mock_load_callback, save_threads_callback=mock_save_callback)

        # Act
        # Call on_run_end (synchronous)
        hooks.on_run_end(context=mock_run_context_wrapper.context, result=mock_run_result)

        # Assert
        # Verify save_threads_callback was called with serialized data (not ConversationThread objects)
        expected_serialized_data = {thread_id_1: {"items": [{"role": "user", "content": "to_save"}], "metadata": {}}}
        mock_save_callback.assert_called_once_with(expected_serialized_data)

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
        thread_id_1 = "user->TestAgent"
        thread_obj = ConversationThread(thread_id=thread_id_1, items=[{"role": "user", "content": "to_save"}])
        mock_thread_manager._threads = {thread_id_1: thread_obj}

        save_error = OSError("Simulated save error")
        # Configure the async mock to raise an error when called
        mock_save_callback.side_effect = save_error

        hooks = PersistenceHooks(load_threads_callback=mock_load_callback, save_threads_callback=mock_save_callback)

        # Act & Assert
        # Verify the hook runs without raising the exception itself (it should catch it)
        try:
            hooks.on_run_end(context=mock_run_context_wrapper.context, result=mock_run_result)
        except Exception as e:
            pytest.fail(f"PersistenceHooks.on_run_end raised an unexpected exception: {e}")

        # Verify save_threads_callback was called with serialized data
        expected_serialized_data = {thread_id_1: {"items": [{"role": "user", "content": "to_save"}], "metadata": {}}}
        mock_save_callback.assert_called_once_with(expected_serialized_data)

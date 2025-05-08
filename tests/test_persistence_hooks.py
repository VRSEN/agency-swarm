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
        # Simulate load_callback returning a dictionary of threads
        chat_id_1 = "unit_test_chat_1"
        chat_id_2 = "unit_test_chat_2"
        loaded_threads_dict = {
            chat_id_1: ConversationThread(thread_id=chat_id_1, items=[{"role": "user", "content": "loaded1"}]),
            chat_id_2: ConversationThread(thread_id=chat_id_2, items=[{"role": "user", "content": "loaded2"}]),
        }
        mock_load_callback.return_value = loaded_threads_dict  # Simulate successful load returning a dict

        hooks = PersistenceHooks(load_callback=mock_load_callback, save_callback=mock_save_callback)

        # Act
        # Call on_run_start only with context (it's synchronous)
        hooks.on_run_start(context=mock_run_context_wrapper.context)

        # Assert
        mock_load_callback.assert_called_once_with()  # Called without arguments
        # Verify thread_manager._threads was populated by the hook
        assert mock_thread_manager._threads == loaded_threads_dict

    @pytest.mark.asyncio
    async def test_on_run_start_load_none(
        self,
        mock_load_callback,
        mock_save_callback,
        mock_thread_manager,
        mock_run_context_wrapper,
    ):
        """Test PersistenceHooks.on_run_start when load_callback returns None."""
        # Arrange
        mock_load_callback.return_value = None  # Simulate load returning None
        initial_threads = mock_thread_manager._threads.copy()

        hooks = PersistenceHooks(load_callback=mock_load_callback, save_callback=mock_save_callback)

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
        """Test PersistenceHooks.on_run_start when load_callback raises an error."""
        # Arrange
        load_error = OSError("Simulated load error")
        mock_load_callback.side_effect = load_error  # Simulate load raising error
        initial_threads = mock_thread_manager._threads.copy()

        hooks = PersistenceHooks(load_callback=mock_load_callback, save_callback=mock_save_callback)

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
        """Test PersistenceHooks.on_run_end successfully calls save_callback."""
        # Arrange
        chat_id_1 = "unit_test_chat_1"
        # Pre-populate the mock thread manager with some data to be saved
        threads_to_save = {
            chat_id_1: ConversationThread(thread_id=chat_id_1, items=[{"role": "user", "content": "to_save"}])
        }
        mock_thread_manager._threads = threads_to_save

        hooks = PersistenceHooks(load_callback=mock_load_callback, save_callback=mock_save_callback)

        # Act
        # Call on_run_end (synchronous)
        hooks.on_run_end(context=mock_run_context_wrapper.context, result=mock_run_result)

        # Assert
        # Verify save_callback (which is async mock) was called correctly
        mock_save_callback.assert_called_once_with(threads_to_save)
        # Note: We don't await the save_callback directly here, just check it was called.
        # The hook calls it synchronously, but the callback itself might do async IO.

    @pytest.mark.asyncio
    async def test_on_run_end_save_error(
        self,
        mock_load_callback,
        mock_save_callback,
        mock_thread_manager,
        mock_run_context_wrapper,
        mock_run_result,
    ):
        """Test PersistenceHooks.on_run_end when save_callback raises an error."""
        # Arrange
        chat_id_1 = "unit_test_chat_1"
        threads_to_save = {
            chat_id_1: ConversationThread(thread_id=chat_id_1, items=[{"role": "user", "content": "to_save"}])
        }
        mock_thread_manager._threads = threads_to_save

        save_error = OSError("Simulated save error")
        # Configure the async mock to raise an error when called
        mock_save_callback.side_effect = save_error

        hooks = PersistenceHooks(load_callback=mock_load_callback, save_callback=mock_save_callback)

        # Act & Assert
        # Verify the hook runs without raising the exception itself (it should catch it)
        try:
            hooks.on_run_end(context=mock_run_context_wrapper.context, result=mock_run_result)
        except Exception as e:
            pytest.fail(f"PersistenceHooks.on_run_end raised an unexpected exception: {e}")

        # Verify save_callback was still called
        mock_save_callback.assert_called_once_with(threads_to_save)
        # Optional: Check logs for error message

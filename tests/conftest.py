from unittest.mock import AsyncMock, MagicMock

import pytest

from agency_swarm import Agent
from agency_swarm.thread import ConversationThread, ThreadManager


@pytest.fixture
def mock_thread_manager():
    """Provides a mocked ThreadManager instance that returns threads with matching IDs."""
    manager = MagicMock(spec=ThreadManager)
    created_threads = {}

    def get_thread_side_effect(thread_id):
        """Side effect for get_thread to create/return mock threads with correct ID."""
        if thread_id not in created_threads:
            mock_thread_fixture_created = MagicMock(spec=ConversationThread)
            mock_thread_fixture_created.thread_id = thread_id
            mock_thread_fixture_created.items = []

            def add_item_side_effect(item):
                mock_thread_fixture_created.items.append(item)

            mock_thread_fixture_created.add_item.side_effect = add_item_side_effect

            def add_items_side_effect(items):
                mock_thread_fixture_created.items.extend(items)

            mock_thread_fixture_created.add_items.side_effect = add_items_side_effect
            mock_thread_fixture_created.get_history.return_value = []
            created_threads[thread_id] = mock_thread_fixture_created
        return created_threads[thread_id]

    manager.get_thread.side_effect = get_thread_side_effect

    def add_items_and_save_side_effect(thread_obj, items_to_add):
        if hasattr(thread_obj, "items") and isinstance(thread_obj.items, list):
            thread_obj.items.extend(items_to_add)
        else:
            pass

    manager.add_item_and_save = MagicMock()
    manager.add_items_and_save = MagicMock(side_effect=add_items_and_save_side_effect)
    return manager


@pytest.fixture
def mock_agency_instance(mock_thread_manager):
    agency = MagicMock()
    agency.agents = {}
    agency.user_context = {}
    agency.thread_manager = mock_thread_manager
    return agency


@pytest.fixture
def minimal_agent(mock_thread_manager, mock_agency_instance):
    """Provides a minimal Agent instance for basic tests."""
    agent = Agent(name="TestAgent", instructions="Test instructions")
    agent._set_agency_instance(mock_agency_instance)
    agent._set_thread_manager(mock_thread_manager)
    mock_agency_instance.agents[agent.name] = agent
    return agent


@pytest.fixture
def mock_agent():
    """Provides a mocked Agent instance for testing."""
    agent = MagicMock(spec=Agent)
    agent.name = "MockAgent"
    agent.get_response = AsyncMock()

    # Create a proper async generator mock for get_response_stream
    async def default_stream(*args, **kwargs):
        yield {"event": "text", "data": "Mock response"}
        yield {"event": "done"}

    agent.get_response_stream = default_stream
    return agent


@pytest.fixture
def mock_agent2():
    """Provides a second mocked Agent instance for testing."""
    agent = MagicMock(spec=Agent)
    agent.name = "MockAgent2"
    agent.get_response = AsyncMock()

    # Create a proper async generator mock for get_response_stream
    async def default_stream(*args, **kwargs):
        yield {"event": "text", "data": "Mock response 2"}
        yield {"event": "done"}

    agent.get_response_stream = default_stream
    return agent

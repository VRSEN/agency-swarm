from unittest.mock import AsyncMock, MagicMock

import pytest
from dotenv import load_dotenv

from agency_swarm import Agency, AgencyContext, Agent
from agency_swarm.utils.thread import ThreadManager

load_dotenv()


@pytest.fixture
def mock_thread_manager():
    """Provides a mocked ThreadManager instance with flat message storage."""
    manager = MagicMock(spec=ThreadManager)
    messages = []

    def add_message_side_effect(message):
        """Side effect for add_message to append to message list."""
        messages.append(message)

    def add_messages_side_effect(msgs):
        """Side effect for add_messages to extend message list."""
        messages.extend(msgs)

    def get_conversation_history_side_effect(agent, caller_agent=None):
        """Side effect for get_conversation_history to filter messages."""
        filtered = []
        for msg in messages:
            if (msg.get("agent") == agent and msg.get("callerAgent") == caller_agent) or (
                msg.get("callerAgent") == agent and msg.get("agent") == caller_agent
            ):
                filtered.append(msg)
        return filtered

    def get_all_messages_side_effect():
        """Side effect for get_all_messages to return all messages."""
        return messages.copy()

    manager.add_message.side_effect = add_message_side_effect
    manager.add_messages.side_effect = add_messages_side_effect
    manager.get_conversation_history.side_effect = get_conversation_history_side_effect
    manager.get_all_messages.side_effect = get_all_messages_side_effect

    # Legacy compatibility - these should not be used but may be called
    manager.get_thread = MagicMock()
    manager.add_item_and_save = MagicMock()
    manager.add_items_and_save = MagicMock()

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

    # Create an agency and replace its thread manager with our mock
    agency = Agency(agent)
    agency.thread_manager = mock_thread_manager

    # Mock the agent's context creation to always return a context with our mock thread manager
    def mock_create_minimal_context():
        return AgencyContext(
            agency_instance=None,
            thread_manager=mock_thread_manager,
            subagents={},
            load_threads_callback=None,
            save_threads_callback=None,
            shared_instructions=None,
        )

    agent._create_minimal_context = mock_create_minimal_context

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

from unittest.mock import MagicMock

import pytest

from agency_swarm import Agency, Agent

# --- Fixtures ---


@pytest.fixture
def mock_agent():
    """Provides a mocked Agent instance for testing."""
    agent = MagicMock(spec=Agent)
    agent.name = "MockAgent"
    agent.send_message_tool_class = None  # Add missing attribute
    return agent


@pytest.fixture
def mock_agent2():
    """Provides a second mocked Agent instance for testing."""
    agent = MagicMock(spec=Agent)
    agent.name = "MockAgent2"
    agent.send_message_tool_class = None  # Add missing attribute
    return agent


# --- Agency Initialization Tests ---


def test_agency_minimal_initialization(mock_agent):
    """Test Agency initialization with minimal parameters using deprecated agency_chart."""
    chart = [mock_agent]
    agency = Agency(agency_chart=chart)
    assert agency.agents == {"MockAgent": mock_agent}
    assert agency.shared_instructions is None or agency.shared_instructions == ""
    assert agency.persistence_hooks is None


def test_agency_initialization_with_flows(mock_agent, mock_agent2):
    """Test Agency initialization with communication flows using deprecated agency_chart."""
    chart = [
        mock_agent,
        [mock_agent, mock_agent2],  # mock_agent can communicate with mock_agent2
    ]
    agency = Agency(agency_chart=chart)
    assert agency.agents == {"MockAgent": mock_agent, "MockAgent2": mock_agent2}
    # Check that agents are properly registered
    assert len(agency.agents) == 2


def test_agency_initialization_shared_instructions(mock_agent):
    """Test Agency initialization with shared instructions."""
    instructions_content = "These are shared instructions for all agents."
    agency = Agency(mock_agent, shared_instructions=instructions_content)
    assert agency.shared_instructions == instructions_content


def test_agency_initialization_persistence_hooks(mock_agent):
    """Test Agency initialization with persistence hooks."""
    mock_load_cb = MagicMock()
    mock_save_cb = MagicMock()
    agency = Agency(mock_agent, load_threads_callback=mock_load_cb, save_threads_callback=mock_save_cb)
    assert agency.persistence_hooks is not None
    # The callbacks are passed to ThreadManager and PersistenceHooks, not stored directly


def test_agency_duplicate_agent_names_forbidden():
    """Test that Agency raises ValueError when trying to register two agents with
    the same name but different instances."""
    # Create two different mock agents with the same name
    agent1 = MagicMock(spec=Agent)
    agent1.name = "DuplicateName"

    agent2 = MagicMock(spec=Agent)
    agent2.name = "DuplicateName"

    # Verify they are different instances
    assert id(agent1) != id(agent2)

    # Attempting to create an Agency with two agents having the same name should raise ValueError
    with pytest.raises(ValueError, match=r"Duplicate agent name 'DuplicateName' with different instances found"):
        Agency(agent1, agent2)


# --- Shared Instruction File Loading Tests ---


def test_agency_shared_instructions_file_loading(tmp_path):
    """Test that agency can load shared instructions from a file."""
    # Create shared instruction file
    shared_file = tmp_path / "shared_instructions.txt"
    shared_content = "All agents must follow these shared guidelines."
    shared_file.write_text(shared_content)

    # Create test agent
    agent = Agent(name="TestAgent", instructions="You are a test agent.", model="gpt-5-mini")

    # Create agency with shared instruction file
    agency = Agency(
        agent,  # Entry point agent as positional argument
        shared_instructions=str(shared_file),
    )

    assert agency.shared_instructions == shared_content


def test_agency_shared_instructions_string():
    """Test that agency accepts instruction strings that aren't files."""
    shared_text = "These are shared instructions as text"

    agent = Agent(name="TestAgent", instructions="Test agent instructions", model="gpt-5-mini")

    agency = Agency(
        agent,  # Entry point agent as positional argument
        shared_instructions=shared_text,
    )

    # Should keep the text as-is since it's not a file
    assert agency.shared_instructions == shared_text


def test_agency_shared_instructions_none():
    """Test agency with no shared instructions."""
    agent = Agent(name="TestAgent", instructions="Test agent", model="gpt-5-mini")

    agency = Agency(
        agent,  # Entry point agent as positional argument
        shared_instructions=None,
    )

    assert agency.shared_instructions == ""


def test_agency_rejects_global_model(mock_agent):
    """Global model parameter is deprecated and must raise an error."""
    with pytest.raises(TypeError, match="Agency no longer accepts a global 'model'"):
        with pytest.warns(DeprecationWarning, match="'model' parameter is deprecated"):
            Agency(mock_agent, model="gpt-4o")

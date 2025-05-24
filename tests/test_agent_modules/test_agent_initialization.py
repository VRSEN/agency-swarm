from unittest.mock import MagicMock

from agents import FunctionTool
from pydantic import BaseModel, Field

from agency_swarm import Agent


class TaskOutput(BaseModel):
    task_name: str = Field(..., description="Name of the task")
    status: str = Field(..., description="Status of the task")
    priority: int = Field(..., description="Priority level (1-5)")


class SimpleOutput(BaseModel):
    message: str = Field(..., description="Simple message")


# --- Initialization Tests ---


def test_agent_initialization_minimal():
    """Test basic Agent initialization with minimal parameters."""
    agent = Agent(name="Agent1", instructions="Be helpful")
    assert agent.name == "Agent1"
    assert agent.instructions == "Be helpful"
    assert agent.tools == []
    assert agent._subagents == {}
    assert agent.files_folder is None
    assert agent.response_validator is None
    assert agent._thread_manager is None
    assert agent._agency_instance is None
    assert agent.output_type is None


def test_agent_initialization_with_tools():
    """Test Agent initialization with tools."""
    tool1 = MagicMock(spec=FunctionTool)
    tool1.name = "tool1"
    agent = Agent(name="Agent2", instructions="Use tools", tools=[tool1])
    assert len(agent.tools) == 1
    assert agent.tools[0] == tool1


def test_agent_initialization_with_model():
    """Test Agent initialization with a specific model."""
    agent = Agent(name="Agent3", instructions="Test", model="gpt-4o-mini")
    assert agent.name == "Agent3"
    assert agent.instructions == "Test"
    assert agent.model == "gpt-4o-mini"


def test_agent_initialization_with_validator():
    """Test Agent initialization with a response validator."""
    validator = MagicMock()
    agent = Agent(name="Agent4", instructions="Validate me", response_validator=validator)
    assert agent.response_validator == validator


def test_agent_initialization_with_output_type():
    """Test Agent initialization with output_type parameter."""
    agent = Agent(name="Agent5", instructions="Structured output", output_type=TaskOutput)
    assert agent.output_type == TaskOutput
    assert agent.name == "Agent5"
    assert agent.instructions == "Structured output"


def test_agent_initialization_with_different_output_types():
    """Test Agent initialization with different output_type parameters."""
    # Test with Pydantic model
    agent1 = Agent(name="Agent1", instructions="Task agent", output_type=TaskOutput)
    assert agent1.output_type == TaskOutput

    # Test with different Pydantic model
    agent2 = Agent(name="Agent2", instructions="Simple agent", output_type=SimpleOutput)
    assert agent2.output_type == SimpleOutput

    # Test without output_type (should be None)
    agent3 = Agent(name="Agent3", instructions="Basic agent")
    assert agent3.output_type is None


def test_agent_initialization_with_all_parameters():
    """Test Agent initialization with all parameters including output_type."""
    validator = MagicMock()
    tool1 = MagicMock(spec=FunctionTool)
    tool1.name = "tool1"

    agent = Agent(
        name="CompleteAgent",
        instructions="Complete agent with all params",
        model="gpt-4o-mini",
        tools=[tool1],
        response_validator=validator,
        output_type=TaskOutput,
        files_folder="./test_files",
        description="A complete test agent",
    )

    assert agent.name == "CompleteAgent"
    assert agent.instructions == "Complete agent with all params"
    assert agent.model == "gpt-4o-mini"
    assert len(agent.tools) == 1
    assert agent.response_validator == validator
    assert agent.output_type == TaskOutput
    assert agent.files_folder == "./test_files"
    assert agent.description == "A complete test agent"


def test_agent_repr():
    """Test Agent.__repr__ method with different configurations."""
    # Test basic agent with minimal config
    agent1 = Agent(name="TestAgent")
    repr_str = repr(agent1)
    assert "name='TestAgent'" in repr_str
    assert "desc=None" in repr_str
    assert "model='unknown'" in repr_str

    # Test agent with model
    agent2 = Agent(name="Worker", model="gpt-4o-mini")
    repr_str = repr(agent2)
    assert "name='Worker'" in repr_str
    assert "model='gpt-4o-mini'" in repr_str

    # Test agent with description and output_type
    agent3 = Agent(name="TaskAgent", description="Handles tasks", output_type=TaskOutput)
    repr_str = repr(agent3)
    assert "name='TaskAgent'" in repr_str
    assert "desc='Handles tasks'" in repr_str

from unittest.mock import MagicMock

from agents import FunctionTool, ModelSettings
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
    assert agent.files_folder is None
    assert not hasattr(agent, "response_validator")
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
    agent = Agent(name="Agent3", instructions="Test", model="gpt-4.1")
    assert agent.name == "Agent3"
    assert agent.instructions == "Test"
    assert agent.model == "gpt-4.1"


def test_agent_initialization_with_validator():
    """Test Agent initialization with response_validator shows deprecation warning."""
    validator = MagicMock()
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        agent = Agent(name="Agent4", instructions="Validate me", response_validator=validator)
        # Should show deprecation warning
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "response_validator" in str(w[0].message)
        # response_validator is completely removed
        assert not hasattr(agent, "response_validator")


def test_agent_initialization_with_output_type():
    """Test Agent initialization with output_type parameter."""
    agent = Agent(name="Agent5", instructions="Structured output", output_type=TaskOutput)
    assert agent.output_type == TaskOutput
    assert agent.name == "Agent5"
    assert agent.instructions == "Structured output"


def test_agent_initialization_with_model_settings():
    """Test Agent initialization with a specific model."""
    agent = Agent(
        name="Agent6",
        instructions="Test",
        model_settings=ModelSettings(
            temperature=0.3,
            max_tokens=16,
            top_p=0.5,
        ),
    )
    assert agent.model_settings.temperature == 0.3
    assert agent.model_settings.max_tokens == 16
    assert agent.model_settings.top_p == 0.5


def test_agent_initialization_with_deprecated_model_settings():
    """Test Agent initialization with a specific model."""
    agent = Agent(
        name="Agent7",
        instructions="Test",
        temperature=0.3,
        max_prompt_tokens=16,  # should be converted to max_tokens
    )
    assert agent.model_settings.temperature == 0.3
    assert agent.model_settings.max_tokens == 16


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

    # TEST-ONLY SETUP: Create test directory to enable FileSearchTool auto-addition
    import tempfile
    from pathlib import Path

    # Create a temporary test directory
    with tempfile.TemporaryDirectory(prefix="test_files_") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        test_file = temp_dir / "test.txt"
        test_file.write_text("test content for FileSearchTool")

        import warnings

        # Mock OpenAI client to avoid requiring API key
        from unittest.mock import patch

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            with patch("agency_swarm.agent_core.OpenAI") as mock_openai:
                mock_client = MagicMock()
                mock_openai.return_value = mock_client
                mock_client.vector_stores.create.return_value = MagicMock(id="vs_test_id")

                agent = Agent(
                    name="CompleteAgent",
                    instructions="Complete agent with all params",
                    model="gpt-4.1",
                    tools=[tool1],
                    response_validator=validator,
                    output_type=TaskOutput,
                    files_folder=str(temp_dir),  # Use temporary directory
                    description="A complete test agent",
                )
            # Should trigger deprecation warning for response_validator
            assert any("response_validator" in str(warning.message) for warning in w)

        assert agent.name == "CompleteAgent"
        assert agent.instructions == "Complete agent with all params"
        assert agent.model == "gpt-4.1"
        assert len(agent.tools) == 2
        assert agent.tools[0] == tool1
        assert agent.tools[1].__class__.__name__ == "FileSearchTool"
        # response_validator is completely removed
        assert not hasattr(agent, "response_validator")
        assert agent.output_type == TaskOutput
        assert str(temp_dir) in str(agent.files_folder)  # Should contain the temp directory path
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
    agent2 = Agent(name="Worker", model="gpt-4.1")
    repr_str = repr(agent2)
    assert "name='Worker'" in repr_str
    assert "model='gpt-4.1'" in repr_str

    # Test agent with description and output_type
    agent3 = Agent(name="TaskAgent", description="Handles tasks", output_type=TaskOutput)
    repr_str = repr(agent3)
    assert "name='TaskAgent'" in repr_str
    assert "desc='Handles tasks'" in repr_str


# --- Instruction File Loading Tests ---


def test_agent_instruction_file_loading(tmp_path):
    """Test that agent can load instructions from a file."""
    # Create instruction file
    instruction_file = tmp_path / "agent_instructions.md"
    instruction_content = "You are a helpful assistant. Always be polite."
    instruction_file.write_text(instruction_content)

    # Create agent with instruction file path
    agent = Agent(name="TestAgent", instructions=str(instruction_file), model="gpt-4o-mini")

    # Verify instructions were loaded
    assert agent.instructions == instruction_content


def test_agent_instruction_file_relative_path(tmp_path):
    """Test agent loading instructions from relative path."""
    import os

    # Create a subdirectory structure
    agent_dir = tmp_path / "agents" / "test_agent"
    agent_dir.mkdir(parents=True)

    instruction_file = agent_dir / "instructions.md"
    instruction_content = "I am a specialized agent for testing."
    instruction_file.write_text(instruction_content)

    # Change to the agent directory
    original_cwd = os.getcwd()
    try:
        os.chdir(agent_dir)

        # Create agent with relative path
        agent = Agent(name="TestAgent", instructions="./instructions.md", model="gpt-4o-mini")

        assert agent.instructions == instruction_content
    finally:
        os.chdir(original_cwd)


def test_agent_instruction_string_not_file():
    """Test that agent accepts instruction strings that aren't files."""
    instruction_text = "Direct instruction text, not a file path"

    agent = Agent(name="TestAgent", instructions=instruction_text, model="gpt-4o-mini")

    # Should keep the text as-is since it's not a file
    assert agent.instructions == instruction_text


def test_agent_missing_instruction_file():
    """Test proper error when instruction file doesn't exist."""
    import pytest

    with pytest.raises(FileNotFoundError) as exc_info:
        Agent(name="TestAgent", instructions="./nonexistent_instructions.md", model="gpt-4o-mini")

    assert "Instructions file not found" in str(exc_info.value)
    assert "nonexistent_instructions.md" in str(exc_info.value)

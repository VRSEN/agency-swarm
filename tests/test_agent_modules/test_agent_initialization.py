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
    from unittest.mock import PropertyMock, patch

    # Create a temporary test directory
    with tempfile.TemporaryDirectory(prefix="test_files_") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        test_file = temp_dir / "test.txt"
        test_file.write_text("test content for FileSearchTool")

        import warnings

        # Mock the OpenAI client to avoid API key requirement
        mock_vector_store = MagicMock()
        mock_vector_store.id = "test_vs_id"

        mock_client = MagicMock()
        mock_client.vector_stores.create.return_value = mock_vector_store

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            with patch.object(Agent, "client_sync", new_callable=PropertyMock) as mock_client_sync:
                mock_client_sync.return_value = mock_client
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


# --- Instruction File Loading Tests ---


def test_agent_instruction_file_loading(tmp_path):
    """Test that agent can load instructions from absolute and relative file paths."""
    # Create instruction file for absolute path test
    instruction_file = tmp_path / "agent_instructions.md"
    instruction_content = "You are a helpful assistant. Always be polite."
    instruction_file.write_text(instruction_content)

    # Absolute path
    agent = Agent(name="TestAgent", instructions=str(instruction_file), model="gpt-5-mini")
    assert agent.instructions == instruction_content

    # Relative path resolved from caller directory
    relative_agent = Agent(name="TestAgent", instructions="../data/files/instructions.md", model="gpt-5-mini")
    assert relative_agent.instructions == "Test instructions"


def test_agent_instruction_string_not_file():
    """Test that agent accepts instruction strings that aren't files."""
    instruction_text = "Direct instruction text, not a file path"

    agent = Agent(name="TestAgent", instructions=instruction_text, model="gpt-5-mini")

    # Should keep the text as-is since it's not a file
    assert agent.instructions == instruction_text


def test_agent_initialization_with_reasoning_effort():
    """Legacy reasoning_effort maps to ModelSettings.reasoning.effort."""
    agent = Agent(name="Reasoner", instructions="Test", reasoning_effort="medium")
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "medium"


def test_agent_initialization_with_truncation_strategy():
    """Legacy truncation_strategy maps to ModelSettings.truncation."""
    agent = Agent(name="Trunc", instructions="Test", truncation_strategy="auto")
    assert agent.model_settings.truncation == "auto"


def test_agent_initialization_response_format_guard():
    """Non-type response_format should be ignored and not set output_type."""
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        agent = Agent(
            name="RF",
            instructions="Test",
            response_format={"type": "json_schema", "json_schema": {"name": "X", "schema": {}}},
        )
    # Ensure a deprecation warning mentioning response_format was raised
    assert any("response_format" in str(item.message) for item in w)
    # And output_type was not set from a dict
    assert agent.output_type is None


def test_agent_initialization_with_both_token_settings_prefers_completion():
    """When both legacy prompt and completion tokens are provided, prefer completion tokens."""
    agent = Agent(
        name="TokenAgent",
        instructions="Test",
        max_prompt_tokens=100,
        max_completion_tokens=150,
    )
    assert agent.model_settings.max_tokens == 150


def test_agent_initialization_response_format_type_sets_output_type():
    """If response_format is a type, it should set output_type."""
    agent = Agent(name="RFType", instructions="Test", response_format=SimpleOutput)
    assert agent.output_type == SimpleOutput


def test_agent_initialization_misc_deprecations_warn_only():
    """Deprecated params should warn and not break initialization."""
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        agent = Agent(
            name="Misc",
            instructions="Test",
            validation_attempts=2,
            id="abc123",
            tool_resources={"vs": 1},
            file_ids=["f1"],
            file_search=True,
            refresh_from_id="old",
        )
    assert agent.name == "Misc"
    msgs = ",".join(str(item.message) for item in w)
    assert "id' parameter" in msgs
    assert "tool_resources" in msgs
    assert "file_ids" in msgs
    assert "file_search" in msgs
    assert "refresh_from_id" in msgs


def test_agent_initialization_adapts_basetool_type():
    """Passing a BaseTool subclass should be adapted to a FunctionTool."""
    from pydantic import Field

    from agency_swarm.tools import BaseTool

    class _T(BaseTool):
        x: str = Field(..., description="x")

        def run(self):
            return self.x

    agent = Agent(name="ToolsAdapt", instructions="Test", tools=[_T])
    # tools should be adapted to FunctionTool instances
    from agents import FunctionTool

    assert len(agent.tools) == 1
    assert isinstance(agent.tools[0], FunctionTool)

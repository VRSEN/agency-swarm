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
    assert agent._subagents == {}
    assert agent.files_folder is None
    assert not hasattr(agent, "response_validator")  # removed completely
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

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
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


def test_agent_initialization_with_persistence_callbacks():
    """Test Agent initialization with persistence callbacks."""

    def mock_load_callback(thread_id: str):
        return {"items": [], "metadata": {}}

    def mock_save_callback(threads_data: dict):
        pass

    agent = Agent(
        name="PersistentAgent",
        instructions="Agent with persistence",
        load_threads_callback=mock_load_callback,
        save_threads_callback=mock_save_callback,
    )

    assert agent.name == "PersistentAgent"
    assert agent._load_threads_callback == mock_load_callback
    assert agent._save_threads_callback == mock_save_callback
    # ThreadManager should not be created until _ensure_thread_manager is called
    assert agent._thread_manager is None


def test_agent_set_persistence_callbacks():
    """Test _set_persistence_callbacks method."""

    def mock_load_callback(thread_id: str):
        return {"items": [], "metadata": {}}

    def mock_save_callback(threads_data: dict):
        pass

    agent = Agent(name="TestAgent", instructions="Test")

    # Initially no callbacks
    assert agent._load_threads_callback is None
    assert agent._save_threads_callback is None
    assert agent._thread_manager is None

    # Set callbacks
    agent._set_persistence_callbacks(
        load_threads_callback=mock_load_callback,
        save_threads_callback=mock_save_callback,
    )

    assert agent._load_threads_callback == mock_load_callback
    assert agent._save_threads_callback == mock_save_callback
    # ThreadManager should be created with callbacks
    assert agent._thread_manager is not None
    assert agent._thread_manager._load_threads_callback == mock_load_callback
    assert agent._thread_manager._save_threads_callback == mock_save_callback


def test_agent_ensure_thread_manager():
    """Test _ensure_thread_manager method."""

    def mock_load_callback(thread_id: str):
        return {"items": [], "metadata": {}}

    def mock_save_callback(threads_data: dict):
        pass

    agent = Agent(
        name="TestAgent",
        instructions="Test",
        load_threads_callback=mock_load_callback,
        save_threads_callback=mock_save_callback,
    )

    # Initially no ThreadManager
    assert agent._thread_manager is None

    # Call _ensure_thread_manager
    agent._ensure_thread_manager()

    # ThreadManager should be created with callbacks
    assert agent._thread_manager is not None
    assert agent._thread_manager._load_threads_callback == mock_load_callback
    assert agent._thread_manager._save_threads_callback == mock_save_callback


def test_agent_ensure_thread_manager_without_callbacks():
    """Test _ensure_thread_manager method without callbacks."""
    agent = Agent(name="TestAgent", instructions="Test")

    # Initially no ThreadManager or callbacks
    assert agent._thread_manager is None
    assert agent._load_threads_callback is None
    assert agent._save_threads_callback is None

    # Call _ensure_thread_manager
    agent._ensure_thread_manager()

    # ThreadManager should be created without callbacks
    assert agent._thread_manager is not None
    assert agent._thread_manager._load_threads_callback is None
    assert agent._thread_manager._save_threads_callback is None

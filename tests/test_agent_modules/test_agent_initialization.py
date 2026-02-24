from unittest.mock import MagicMock

import pytest
from agents import FunctionTool, ModelSettings, StopAtTools, WebSearchTool
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


def test_agent_initialization_with_stop_at_tools_object():
    """Agent accepts StopAtTools typed dict for tool_use_behavior."""
    behavior = StopAtTools(stop_at_tool_names=["ToolA", "ToolB"])
    agent = Agent(name="AgentStopAtTools", instructions="Test", tool_use_behavior=behavior)

    assert agent.tool_use_behavior == behavior


def test_agent_initialization_with_stop_at_tools_dict():
    """Agent accepts plain StopAtTools-compatible dict for tool_use_behavior."""
    behavior_dict = {"stop_at_tool_names": ["ToolC"]}
    agent = Agent(name="AgentStopAtToolsDict", instructions="Test", tool_use_behavior=behavior_dict)

    assert agent.tool_use_behavior == behavior_dict


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
    """Deprecated direct model settings kwargs must fail fast."""
    with pytest.raises(TypeError, match=r"Deprecated Agent parameters are not supported"):
        Agent(
            name="Agent7",
            instructions="Test",
            temperature=0.3,
            max_prompt_tokens=16,
        )


def test_agent_initialization_with_return_input_guardrail_errors_fails_fast():
    """Removed guardrail kwarg should fail fast with migration guidance."""
    with pytest.raises(TypeError) as exc_info:
        Agent(
            name="LegacyGuardrailAgent",
            instructions="Test",
            return_input_guardrail_errors=False,
        )
    error_message = str(exc_info.value)
    assert "return_input_guardrail_errors" in error_message
    assert "raise_input_guardrail_error" in error_message


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


def test_agent_initialization_with_raise_input_guardrail_error_flag():
    """Canonical kwarg should set the runtime flag."""
    agent = Agent(
        name="AliasAgent",
        instructions="Test",
        raise_input_guardrail_error=True,
    )
    assert agent.raise_input_guardrail_error is True


def test_agent_initialization_with_deprecated_throw_input_guardrail_error_warns():
    """Deprecated alias should still work and emit a deprecation warning."""
    with pytest.warns(DeprecationWarning, match=r"throw_input_guardrail_error"):
        agent = Agent(
            name="AliasDeprecatedAgent",
            instructions="Test",
            throw_input_guardrail_error=True,
        )
    assert agent.raise_input_guardrail_error is True


def test_agent_initialization_with_matching_raise_and_throw_input_guardrail_error():
    """Matching alias+canonical values should be accepted."""
    with pytest.warns(DeprecationWarning, match=r"throw_input_guardrail_error"):
        agent = Agent(
            name="AliasMatchAgent",
            instructions="Test",
            raise_input_guardrail_error=False,
            throw_input_guardrail_error=False,
        )
    assert agent.raise_input_guardrail_error is False


def test_agent_initialization_with_conflicting_raise_and_throw_input_guardrail_error():
    """Conflicting alias+canonical values should fail fast."""
    with pytest.raises(TypeError, match=r"Conflicting values for `raise_input_guardrail_error`"):
        Agent(
            name="AliasConflictAgent",
            instructions="Test",
            raise_input_guardrail_error=True,
            throw_input_guardrail_error=False,
        )


def test_agent_throw_input_guardrail_error_property_alias_maps_to_canonical():
    """Runtime property alias should map to canonical storage."""
    agent = Agent(
        name="AliasPropertyAgent",
        instructions="Test",
        raise_input_guardrail_error=True,
    )
    assert agent.throw_input_guardrail_error is True
    agent.throw_input_guardrail_error = False
    assert agent.raise_input_guardrail_error is False


def test_agent_initialization_with_all_parameters():
    """Test Agent initialization with all parameters including output_type."""
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

        # Mock the OpenAI client to avoid API key requirement
        mock_vector_store = MagicMock()
        mock_vector_store.id = "test_vs_id"

        mock_client = MagicMock()
        mock_client.vector_stores.create.return_value = mock_vector_store
        uploaded_file = MagicMock()
        uploaded_file.id = "file-1234567890abcdef"
        uploaded_file.created_at = 1_735_689_600
        mock_client.files.create.return_value = uploaded_file
        vs_file = MagicMock()
        vs_file.status = "completed"
        mock_client.vector_stores.files.retrieve.return_value = vs_file
        # Prevent infinite pagination when syncing vector store files during init
        list_resp = MagicMock()
        list_resp.data = []
        list_resp.has_more = False
        list_resp.last_id = None
        mock_client.vector_stores.files.list.return_value = list_resp

        with patch.object(Agent, "client_sync", new_callable=PropertyMock) as mock_client_sync:
            mock_client_sync.return_value = mock_client
            agent = Agent(
                name="CompleteAgent",
                instructions="Complete agent with all params",
                model="gpt-5-mini",
                tools=[tool1],
                output_type=TaskOutput,
                files_folder=str(temp_dir),  # Use temporary directory
                description="A complete test agent",
            )

        assert agent.name == "CompleteAgent"
        assert agent.instructions == "Complete agent with all params"
        assert agent.model == "gpt-5-mini"
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
    """Deprecated reasoning_effort must fail fast."""
    with pytest.raises(TypeError, match=r"reasoning_effort"):
        Agent(name="Reasoner", instructions="Test", reasoning_effort="medium")


def test_agent_initialization_defaults_truncation_to_auto():
    """Default ModelSettings should prefer truncation='auto'."""
    agent = Agent(name="TruncDefault", instructions="Test")
    assert agent.model_settings.truncation == "auto"


def test_agent_initialization_preserves_explicit_truncation_disabled():
    """Explicit truncation='disabled' should not be overwritten by the default."""
    agent = Agent(
        name="TruncDisabled",
        instructions="Test",
        model_settings=ModelSettings(truncation="disabled"),
    )
    assert agent.model_settings.truncation == "disabled"


def test_agent_initialization_applies_sdk_model_defaults():
    """Model-specific SDK defaults (e.g., GPT-5 reasoning) should be preserved."""
    agent = Agent(name="Gpt5", instructions="Test", model="gpt-5-mini")
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "low"


def test_agent_initialization_with_truncation_strategy():
    """Deprecated truncation_strategy must fail fast."""
    with pytest.raises(TypeError, match=r"truncation_strategy"):
        Agent(name="Trunc", instructions="Test", truncation_strategy="auto")


def test_agent_initialization_response_format_guard():
    """Deprecated response_format must fail fast (even when it is a dict)."""
    with pytest.raises(TypeError, match=r"response_format"):
        Agent(
            name="RF",
            instructions="Test",
            response_format={"type": "json_schema", "json_schema": {"name": "X", "schema": {}}},
        )


def test_agent_initialization_with_both_token_settings_prefers_completion():
    """Deprecated token kwargs must fail fast."""
    with pytest.raises(TypeError, match=r"max_prompt_tokens"):
        Agent(
            name="TokenAgent",
            instructions="Test",
            max_prompt_tokens=100,
            max_completion_tokens=150,
        )


def test_agent_initialization_response_format_type_sets_output_type():
    """Deprecated response_format must fail fast (even when it is a type)."""
    with pytest.raises(TypeError, match=r"response_format"):
        Agent(name="RFType", instructions="Test", response_format=SimpleOutput)


def test_agent_initialization_misc_deprecations_warn_only():
    """Deprecated init params must fail fast (no warning path)."""
    with pytest.raises(TypeError, match=r"Deprecated Agent parameters are not supported"):
        Agent(
            name="Misc",
            instructions="Test",
            validation_attempts=2,
            id="abc123",
            tool_resources={"vs": 1},
            file_ids=["f1"],
            file_search=True,
            refresh_from_id="old",
            send_message_tool_class=object,
        )


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


def test_agent_initialization_includes_web_search_sources_by_default():
    """WebSearchTool should opt into source URLs by default."""
    agent = Agent(name="WebAgentDefault", instructions="Test", tools=[WebSearchTool()])
    includes = agent.model_settings.response_include or []
    assert "web_search_call.action.sources" in includes


def test_agent_initialization_can_disable_web_search_sources_include():
    """Users should be able to opt out from automatic web search sources include."""
    agent = Agent(
        name="WebAgentNoSources",
        instructions="Test",
        tools=[WebSearchTool()],
        include_web_search_sources=False,
    )
    includes = agent.model_settings.response_include or []
    assert "web_search_call.action.sources" not in includes


def test_agent_initialization_preserves_existing_response_include_with_web_search():
    """Automatic web-search include should merge with existing response_include values."""
    agent = Agent(
        name="WebAgentMergeSources",
        instructions="Test",
        tools=[WebSearchTool()],
        model_settings=ModelSettings(response_include=["message.output_text.logprobs"]),
    )
    includes = agent.model_settings.response_include or []
    assert "message.output_text.logprobs" in includes
    assert "web_search_call.action.sources" in includes


def test_agent_initialization_does_not_duplicate_web_search_sources_include():
    """Automatic web-search include should avoid duplicate include values."""
    agent = Agent(
        name="WebAgentDedupSources",
        instructions="Test",
        tools=[WebSearchTool()],
        model_settings=ModelSettings(response_include=["web_search_call.action.sources"]),
    )
    includes = agent.model_settings.response_include or []
    assert includes.count("web_search_call.action.sources") == 1


def test_agent_add_tool_includes_web_search_sources_by_default():
    """Adding WebSearchTool after init should also add source include."""
    agent = Agent(name="WebAgentAddTool", instructions="Test")
    assert (agent.model_settings.response_include or []) == []

    agent.add_tool(WebSearchTool())

    includes = agent.model_settings.response_include or []
    assert "web_search_call.action.sources" in includes


def test_agent_add_tool_respects_web_search_sources_opt_out():
    """Adding WebSearchTool should not inject include when opt-out is disabled."""
    agent = Agent(
        name="WebAgentAddToolNoSources",
        instructions="Test",
        include_web_search_sources=False,
    )
    agent.add_tool(WebSearchTool())

    includes = agent.model_settings.response_include or []
    assert "web_search_call.action.sources" not in includes

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from agents import FunctionTool, ModelSettings, StopAtTools, WebSearchTool
from pydantic import BaseModel, Field

from agency_swarm import Agent
from agency_swarm.integrations.openclaw_model import build_openclaw_responses_model


class TaskOutput(BaseModel):
    task_name: str = Field(..., description="Name of the task")
    status: str = Field(..., description="Status of the task")
    priority: int = Field(..., description="Priority level (1-5)")


class SimpleOutput(BaseModel):
    message: str = Field(..., description="Simple message")


# --- Initialization Tests ---


def test_agent_initialization_with_stop_at_tools_variants():
    """Agent should accept StopAtTools-typed and dict-compatible tool_use_behavior values."""
    cases = [
        StopAtTools(stop_at_tool_names=["ToolA", "ToolB"]),
        {"stop_at_tool_names": ["ToolC"]},
    ]
    for behavior in cases:
        agent = Agent(name="AgentStopAtTools", instructions="Test", tool_use_behavior=behavior)
        assert agent.tool_use_behavior == behavior


def test_agent_initialization_core_configuration_variants():
    """Core initialization should preserve baseline defaults and explicit tool/model/output settings."""
    minimal = Agent(name="Agent1", instructions="Be helpful")
    assert minimal.name == "Agent1"
    assert minimal.instructions == "Be helpful"
    assert minimal.model == "gpt-5.4-mini"
    assert minimal.tools == []
    assert minimal.files_folder is None
    assert not hasattr(minimal, "response_validator")
    assert minimal.output_type is None

    tool = MagicMock(spec=FunctionTool)
    tool.name = "tool1"
    configured = Agent(
        name="ConfiguredAgent",
        instructions="Use tools",
        tools=[tool],
        model_settings=ModelSettings(
            temperature=0.3,
            max_tokens=16,
            top_p=0.5,
        ),
        output_type=SimpleOutput,
    )
    assert configured.tools == [tool]
    assert configured.model_settings.temperature == 0.3
    assert configured.model_settings.max_tokens == 16
    assert configured.model_settings.top_p == 0.5
    assert configured.output_type == SimpleOutput


def test_agent_initialization_rejects_deprecated_kwargs() -> None:
    """Deprecated initialization kwargs should fail fast with clear errors."""
    cases: list[tuple[dict[str, object], str]] = [
        (
            {"temperature": 0.3, "max_prompt_tokens": 16},
            r"Deprecated Agent parameters are not supported",
        ),
        (
            {"reasoning_effort": "medium"},
            r"reasoning_effort",
        ),
        (
            {"truncation_strategy": "auto"},
            r"truncation_strategy",
        ),
        (
            {"response_format": {"type": "json_schema", "json_schema": {"name": "X", "schema": {}}}},
            r"response_format",
        ),
        (
            {"response_format": SimpleOutput},
            r"response_format",
        ),
        (
            {"max_prompt_tokens": 100, "max_completion_tokens": 150},
            r"max_prompt_tokens",
        ),
        (
            {
                "validation_attempts": 2,
                "id": "abc123",
                "tool_resources": {"vs": 1},
                "file_ids": ["f1"],
                "file_search": True,
                "refresh_from_id": "old",
                "send_message_tool_class": object,
            },
            r"Deprecated Agent parameters are not supported",
        ),
    ]
    for kwargs, message in cases:
        with pytest.raises(TypeError, match=message):
            Agent(name="DeprecatedKwargsAgent", instructions="Test", **kwargs)


def test_agent_initialization_output_type_variants():
    """Explicit output types should be preserved while omitted output_type stays None."""
    assert Agent(name="TaskAgent", instructions="Task agent", output_type=TaskOutput).output_type == TaskOutput
    assert Agent(name="SimpleAgent", instructions="Simple agent", output_type=SimpleOutput).output_type == SimpleOutput
    assert Agent(name="BasicAgent", instructions="Basic agent").output_type is None


def test_agent_initialization_guardrail_flag_aliases_and_failures() -> None:
    """Guardrail aliases should map consistently and fail fast for conflicts/legacy kwargs."""
    canonical_agent = Agent(
        name="AliasCanonicalAgent",
        instructions="Test",
        raise_input_guardrail_error=True,
    )
    assert canonical_agent.raise_input_guardrail_error is True

    with pytest.warns(DeprecationWarning, match=r"throw_input_guardrail_error"):
        deprecated_alias_agent = Agent(
            name="AliasDeprecatedAgent",
            instructions="Test",
            throw_input_guardrail_error=True,
        )
    assert deprecated_alias_agent.raise_input_guardrail_error is True

    with pytest.warns(DeprecationWarning, match=r"throw_input_guardrail_error"):
        matching_alias_agent = Agent(
            name="AliasMatchAgent",
            instructions="Test",
            raise_input_guardrail_error=False,
            throw_input_guardrail_error=False,
        )
    assert matching_alias_agent.raise_input_guardrail_error is False

    with pytest.raises(TypeError, match=r"Conflicting values for `raise_input_guardrail_error`"):
        Agent(
            name="AliasConflictAgent",
            instructions="Test",
            raise_input_guardrail_error=True,
            throw_input_guardrail_error=False,
        )

    with pytest.raises(TypeError) as exc_info:
        Agent(
            name="LegacyGuardrailAgent",
            instructions="Test",
            return_input_guardrail_errors=False,
        )
    error_message = str(exc_info.value)
    assert "return_input_guardrail_errors" in error_message
    assert "raise_input_guardrail_error" in error_message

    agent = Agent(
        name="AliasPropertyAgent",
        instructions="Test",
        raise_input_guardrail_error=True,
    )
    assert agent.throw_input_guardrail_error is True
    agent.throw_input_guardrail_error = False
    assert agent.raise_input_guardrail_error is False


def test_agent_initialization_support_flags_override_defaults() -> None:
    """Capability flags should persist when a plain Agent overrides them."""
    agent = Agent(
        name="RestrictedAgent",
        instructions="Test",
        supports_outbound_communication=False,
        supports_framework_tool_wiring=False,
    )

    assert agent.supports_outbound_communication is False
    assert agent.supports_framework_tool_wiring is False


def test_agent_initialization_skips_framework_tool_wiring_when_disabled(tmp_path) -> None:
    """Framework-managed tool folders should be ignored when tool wiring is disabled."""
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    (tools_dir / "loaded_tool.py").write_text(
        "from agents import function_tool\n\n@function_tool\ndef loaded_tool() -> str:\n    return 'loaded'\n",
        encoding="utf-8",
    )

    agent = Agent(
        name="RestrictedAgent",
        instructions="Test",
        tools_folder=str(tools_dir),
        supports_framework_tool_wiring=False,
    )

    assert agent.tools == []


def test_agent_initialization_keeps_explicit_files_folder_when_framework_tool_wiring_disabled(tmp_path) -> None:
    """Explicit files_folder support should survive even when framework-managed tool wiring is disabled."""
    files_dir = tmp_path / "docs_vs_abcdefghijklmnop"
    files_dir.mkdir()

    agent = Agent(
        name="RestrictedAgent",
        instructions="Test",
        files_folder=str(files_dir),
        supports_framework_tool_wiring=False,
    )

    assert agent._associated_vector_store_id == "vs_abcdefghijklmnop"
    assert [tool.__class__.__name__ for tool in agent.tools] == ["FileSearchTool"]


def test_agent_initialization_converts_explicit_mcp_servers_when_framework_tool_wiring_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    converted: list[str] = []

    def _convert(agent: Agent) -> None:
        converted.append(agent.name)

    monkeypatch.setattr("agency_swarm.agent.core.convert_mcp_servers_to_tools", _convert)

    Agent(
        name="RestrictedAgent",
        instructions="Test",
        mcp_servers=[SimpleNamespace(name="demo")],
        supports_framework_tool_wiring=False,
    )

    assert converted == ["RestrictedAgent"]


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
                model="gpt-5.4-mini",
                tools=[tool1],
                output_type=TaskOutput,
                files_folder=str(temp_dir),  # Use temporary directory
                description="A complete test agent",
            )

        assert agent.name == "CompleteAgent"
        assert agent.instructions == "Complete agent with all params"
        assert agent.model == "gpt-5.4-mini"
        assert len(agent.tools) == 2
        assert agent.tools[0] == tool1
        assert agent.tools[1].__class__.__name__ == "FileSearchTool"
        # response_validator is completely removed
        assert not hasattr(agent, "response_validator")
        assert agent.output_type == TaskOutput
        assert str(temp_dir) in str(agent.files_folder)  # Should contain the temp directory path
        assert agent.description == "A complete test agent"


# --- Instruction File Loading Tests ---


def test_agent_instruction_loading_variants(tmp_path):
    """Instruction inputs should support file paths while preserving plain strings."""
    # Create instruction file for absolute path test
    instruction_file = tmp_path / "agent_instructions.md"
    instruction_content = "You are a helpful assistant. Always be polite."
    instruction_file.write_text(instruction_content)

    # Absolute path
    agent = Agent(name="TestAgent", instructions=str(instruction_file), model="gpt-5.4-mini")
    assert agent.instructions == instruction_content

    # Relative path resolved from caller directory
    relative_agent = Agent(name="TestAgent", instructions="../data/files/instructions.md", model="gpt-5.4-mini")
    assert relative_agent.instructions == "Test instructions"

    instruction_text = "Direct instruction text, not a file path"
    agent = Agent(name="TestAgent", instructions=instruction_text, model="gpt-5.4-mini")
    assert agent.instructions == instruction_text


def test_agent_initialization_model_settings_defaults_and_overrides():
    """Initialization should keep SDK defaults and preserve explicit settings overrides."""
    default_agent = Agent(name="TruncDefault", instructions="Test")
    assert default_agent.model_settings.truncation == "auto"

    explicit_agent = Agent(
        name="TruncDisabled",
        instructions="Test",
        model_settings=ModelSettings(truncation="disabled"),
    )
    assert explicit_agent.model_settings.truncation == "disabled"

    gpt5_agent = Agent(name="Gpt5", instructions="Test", model="gpt-5.4-mini")
    assert gpt5_agent.model_settings.reasoning is not None
    assert gpt5_agent.model_settings.reasoning.effort == "low"

    provider_prefixed_gpt5_agent = Agent(name="ProviderPrefixedGpt5", instructions="Test", model="openai/gpt-5.4-mini")
    assert provider_prefixed_gpt5_agent.model_settings.reasoning is None
    assert provider_prefixed_gpt5_agent.model_settings.verbosity is None


@pytest.mark.parametrize("provider_model", ["openai/gpt-5.4-mini", "azure/gpt-5.4-mini"])
def test_agent_initialization_model_objects_use_openclaw_default_settings_alias(
    monkeypatch: pytest.MonkeyPatch,
    provider_model: str,
) -> None:
    monkeypatch.setenv("OPENCLAW_PROVIDER_MODEL", provider_model)
    model = build_openclaw_responses_model(base_url="http://127.0.0.1:18789/v1", api_key="test-key")

    agent = Agent(name="UsageTrackedModel", instructions="Test", model=model)

    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "low"
    assert agent.model_settings.verbosity == "low"


def test_agent_initialization_model_objects_preserve_explicit_openclaw_alias_defaults() -> None:
    model = build_openclaw_responses_model(
        model="openclaw:custom",
        base_url="http://127.0.0.1:18789/v1",
        api_key="test-key",
    )

    agent = Agent(name="UsageTrackedModel", instructions="Test", model=model)

    assert agent.model_settings.reasoning is None
    assert agent.model_settings.verbosity is None


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


def test_agent_initialization_web_search_source_include_behavior() -> None:
    """Web-search source include should support init and add_tool behavior with merge and opt-out."""
    cases: list[tuple[Agent, bool, int, str | None]] = [
        (
            Agent(name="WebAgentDefault", instructions="Test", tools=[WebSearchTool()]),
            True,
            1,
            None,
        ),
        (
            Agent(
                name="WebAgentNoSources",
                instructions="Test",
                tools=[WebSearchTool()],
                include_web_search_sources=False,
            ),
            False,
            0,
            None,
        ),
        (
            Agent(
                name="WebAgentMergeSources",
                instructions="Test",
                tools=[WebSearchTool()],
                model_settings=ModelSettings(response_include=["message.output_text.logprobs"]),
            ),
            True,
            1,
            "message.output_text.logprobs",
        ),
        (
            Agent(
                name="WebAgentDedupSources",
                instructions="Test",
                tools=[WebSearchTool()],
                model_settings=ModelSettings(response_include=["web_search_call.action.sources"]),
            ),
            True,
            1,
            None,
        ),
    ]
    for agent, has_sources, count, extra_include in cases:
        includes = agent.model_settings.response_include or []
        assert ("web_search_call.action.sources" in includes) is has_sources
        assert includes.count("web_search_call.action.sources") == count
        if extra_include is not None:
            assert extra_include in includes

    add_tool_default = Agent(name="WebAgentAddTool", instructions="Test")
    assert (add_tool_default.model_settings.response_include or []) == []
    add_tool_default.add_tool(WebSearchTool())
    assert "web_search_call.action.sources" in (add_tool_default.model_settings.response_include or [])

    add_tool_opt_out = Agent(
        name="WebAgentAddToolNoSources",
        instructions="Test",
        include_web_search_sources=False,
    )
    add_tool_opt_out.add_tool(WebSearchTool())
    assert "web_search_call.action.sources" not in (add_tool_opt_out.model_settings.response_include or [])

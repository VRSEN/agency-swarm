import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from agents import (
    FunctionTool,
    ModelSettings,
    RunConfig,
    StopAtTools,
    Tool,
    WebSearchTool,
    function_tool as sdk_function_tool,
    handoff as sdk_handoff,
)
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff as SDKHandoff
from agents.items import ModelResponse, TResponseInputItem, TResponseStreamEvent
from agents.models.interface import Model, ModelTracing
from openai.types.responses.response_prompt_param import ResponsePromptParam
from openai.types.shared import Reasoning
from pydantic import BaseModel, Field

from agency_swarm import Agent
from agency_swarm.agent.initialization import (
    normalize_incompatible_model_settings,
    use_runner_compatible_model_settings,
)
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
        model="gpt-4.1-mini",
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
    assert default_agent.model_settings.reasoning is not None
    assert default_agent.model_settings.reasoning.effort == "none"
    assert default_agent.model_settings.verbosity == "low"

    explicit_agent = Agent(
        name="TruncDisabled",
        instructions="Test",
        model_settings=ModelSettings(truncation="disabled"),
    )
    assert explicit_agent.model_settings.truncation == "disabled"

    gpt5_agent = Agent(name="Gpt5", instructions="Test", model="gpt-5.4-mini")
    assert gpt5_agent.model_settings.reasoning is not None
    assert gpt5_agent.model_settings.reasoning.effort == "none"

    provider_prefixed_gpt5_agent = Agent(name="ProviderPrefixedGpt5", instructions="Test", model="openai/gpt-5.4-mini")
    assert provider_prefixed_gpt5_agent.model_settings.reasoning is None
    assert provider_prefixed_gpt5_agent.model_settings.verbosity is None


def test_agent_initialization_model_default_paths_are_consistent() -> None:
    """Omitted model and explicit None should resolve to the same model/settings pair."""
    omitted_model_agent = Agent(name="OmittedModel", instructions="Test")
    none_model_agent = Agent(name="NoneModel", instructions="Test", model=None)
    explicit_model_agent = Agent(name="ExplicitModel", instructions="Test", model="gpt-4.1-mini")

    for agent in (omitted_model_agent, none_model_agent):
        assert agent.model == "gpt-5.4-mini"
        assert agent.model_settings.truncation == "auto"
        assert agent.model_settings.reasoning is not None
        assert agent.model_settings.reasoning.effort == "none"
        assert agent.model_settings.verbosity == "low"

    assert explicit_model_agent.model == "gpt-4.1-mini"
    assert explicit_model_agent.model_settings.truncation == "auto"
    assert explicit_model_agent.model_settings.reasoning is None
    assert explicit_model_agent.model_settings.verbosity is None


@pytest.mark.parametrize(
    ("model_name", "expected_effort"),
    [
        ("gpt-5.4-mini", "low"),
        ("openai/gpt-5.4-mini", "low"),
        ("gpt-5.4-pro", "medium"),
    ],
)
def test_agent_initialization_normalizes_unsupported_gpt5_minimal_reasoning(
    model_name: str,
    expected_effort: str,
) -> None:
    with pytest.warns(UserWarning, match="does not support reasoning.effort='minimal'"):
        agent = Agent(
            name="CompatAgent",
            instructions="Test",
            model=model_name,
            model_settings=ModelSettings(reasoning=Reasoning(effort="minimal")),
        )

    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == expected_effort


@pytest.mark.parametrize(
    "model_name",
    [
        "gpt-5",
        "openai/gpt-5",
        "gpt-5.4-mini",
        "openai/gpt-5.4-mini",
        "o1",
        "o3",
        "o4-mini",
    ],
)
def test_runner_settings_omit_temperature_for_models_with_unsupported_temperature(
    model_name: str,
) -> None:
    with pytest.warns(UserWarning, match="does not support temperature"):
        settings = normalize_incompatible_model_settings(
            model_name,
            ModelSettings(temperature=0.3),
            omit_unsupported_temperature=True,
        )

    assert settings.temperature is None


@pytest.mark.asyncio
async def test_runner_settings_context_normalizes_run_config_model_override_agent_settings() -> None:
    """Per-run model overrides should use compatible agent settings without mutating the agent."""
    agent = Agent(
        name="CompatAgent",
        instructions="Test",
        model="gpt-4.1-mini",
        model_settings=ModelSettings(temperature=0.3, max_tokens=16),
    )
    run_config = RunConfig(model="gpt-5.4-mini")

    with pytest.warns(UserWarning, match="does not support temperature"):
        async with use_runner_compatible_model_settings(agent, run_config) as compatible_run:
            assert compatible_run.agent is agent
            assert agent.model_settings.temperature is None
            assert agent.model_settings.max_tokens == 16
            assert agent.model_settings.reasoning is not None
            assert agent.model_settings.reasoning.effort == "none"
            assert agent.model_settings.verbosity == "low"
            assert compatible_run.run_config is not run_config
            assert compatible_run.run_config.model_settings is None

    assert agent.model_settings.temperature == 0.3
    assert agent.model_settings.max_tokens == 16
    assert run_config.model_settings is None


@pytest.mark.asyncio
async def test_runner_settings_context_strips_gpt5_defaults_for_non_gpt5_model_override() -> None:
    """RunConfig model overrides should recompute model-family settings for the request model."""
    agent = Agent(
        name="CompatAgent",
        instructions="Test",
        model="gpt-5.4-mini",
        model_settings=ModelSettings(temperature=0.3, max_tokens=16, extra_headers={"x-caller": "1"}),
    )
    original_settings = agent.model_settings
    assert original_settings.reasoning is not None
    assert original_settings.verbosity == "low"
    run_config = RunConfig(model="gpt-4.1-mini")

    async with use_runner_compatible_model_settings(agent, run_config) as compatible_run:
        assert compatible_run.agent is agent
        assert compatible_run.run_config is not run_config
        assert agent.model_settings.reasoning is None
        assert agent.model_settings.verbosity is None
        assert agent.model_settings.temperature == 0.3
        assert agent.model_settings.max_tokens == 16
        assert agent.model_settings.extra_headers == {"x-caller": "1"}

    assert agent.model_settings is original_settings
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.verbosity == "low"


@pytest.mark.asyncio
async def test_runner_settings_context_strips_stale_gpt5_reasoning_for_codex_model_override() -> None:
    """RunConfig Codex model overrides should use target family defaults, not stale GPT-5 reasoning."""
    agent = Agent(
        name="CompatAgent",
        instructions="Test",
        model="gpt-5.4-mini",
        model_settings=ModelSettings(max_tokens=16, extra_headers={"x-caller": "1"}),
    )
    original_settings = agent.model_settings
    assert original_settings.reasoning is not None
    assert original_settings.reasoning.effort == "none"
    assert original_settings.verbosity == "low"
    run_config = RunConfig(model="gpt-5.4-codex")

    async with use_runner_compatible_model_settings(agent, run_config) as compatible_run:
        assert compatible_run.agent is agent
        assert compatible_run.run_config is not run_config
        assert agent.model_settings.reasoning is None
        assert agent.model_settings.verbosity == "low"
        assert agent.model_settings.max_tokens == 16
        assert agent.model_settings.extra_headers == {"x-caller": "1"}

    assert agent.model_settings is original_settings
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "none"
    assert agent.model_settings.verbosity == "low"


@pytest.mark.asyncio
async def test_runner_settings_context_normalizes_and_preserves_run_config_settings() -> None:
    """RunConfig settings should remain available for handoffs after compatibility normalization."""
    agent = Agent(name="CompatAgent", instructions="Test", model="gpt-5.4-mini")
    run_config = RunConfig(model_settings=ModelSettings(temperature=0.3, max_tokens=16))

    with pytest.warns(UserWarning, match="does not support temperature"):
        async with use_runner_compatible_model_settings(agent, run_config) as compatible_run:
            assert compatible_run.agent is agent
            assert compatible_run.run_config is not run_config
            assert compatible_run.run_config.model_settings is not None
            assert compatible_run.run_config.model_settings.temperature is None
            assert compatible_run.run_config.model_settings.max_tokens == 16
            assert run_config.model_settings is not None
            assert run_config.model_settings.temperature == 0.3
            assert run_config.model_settings.max_tokens == 16

    assert run_config.model_settings is not None
    assert run_config.model_settings.temperature == 0.3
    assert run_config.model_settings.max_tokens == 16


@pytest.mark.asyncio
async def test_runner_settings_context_normalizes_global_run_settings_for_mixed_handoffs() -> None:
    """Global RunConfig settings should be safe for every protected handoff target."""
    handoff_agent = Agent(name="Gpt5Handoff", instructions="Test", model="gpt-5.4-mini")
    agent = Agent(
        name="Gpt4Root",
        instructions="Test",
        model="gpt-4.1-mini",
        handoffs=[sdk_handoff(handoff_agent)],
    )
    original_agent_settings = agent.model_settings
    original_handoff_settings = handoff_agent.model_settings
    run_config = RunConfig(model_settings=ModelSettings(temperature=0.3, max_tokens=16))
    original_run_settings = run_config.model_settings

    with pytest.warns(UserWarning, match="does not support temperature"):
        async with use_runner_compatible_model_settings(agent, run_config) as compatible_run:
            assert compatible_run.agent is agent
            assert compatible_run.run_config is not run_config
            assert compatible_run.run_config.model_settings is not None
            assert compatible_run.run_config.model_settings is not original_run_settings
            assert compatible_run.run_config.model_settings.temperature is None
            assert compatible_run.run_config.model_settings.max_tokens == 16
            assert run_config.model_settings is original_run_settings
            assert run_config.model_settings.temperature == 0.3

    assert agent.model_settings is original_agent_settings
    assert handoff_agent.model_settings is original_handoff_settings
    assert run_config.model_settings is original_run_settings
    assert run_config.model_settings.temperature == 0.3
    assert run_config.model_settings.max_tokens == 16


@pytest.mark.asyncio
async def test_runner_settings_context_serializes_shared_agent_settings() -> None:
    """Concurrent compatibility windows should serialize shared Agent model settings."""
    agent = Agent(
        name="CompatAgent",
        instructions="Test",
        model="gpt-4.1-mini",
        model_settings=ModelSettings(
            temperature=0.3,
            max_tokens=16,
            reasoning=Reasoning(effort="minimal"),
        ),
    )
    first_run_config = RunConfig(model="gpt-5.4-mini")
    second_run_config = RunConfig(model="gpt-4.1-mini")
    original_settings = agent.model_settings
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    second_entered = asyncio.Event()

    async def first_run() -> None:
        with pytest.warns(UserWarning) as warnings:
            async with use_runner_compatible_model_settings(agent, first_run_config) as compatible_run:
                assert compatible_run.agent is agent
                assert any("does not support temperature" in str(warning.message) for warning in warnings)
                assert any(
                    "does not support reasoning.effort='minimal'" in str(warning.message) for warning in warnings
                )
                assert agent.model_settings.temperature is None
                assert agent.model_settings.reasoning is not None
                assert agent.model_settings.reasoning.effort == "low"
                first_entered.set()
                await release_first.wait()

    async def second_run() -> None:
        await first_entered.wait()
        async with use_runner_compatible_model_settings(agent, second_run_config) as compatible_run:
            assert compatible_run.agent is agent
            second_entered.set()
            assert agent.model_settings.temperature == 0.3
            assert agent.model_settings.reasoning is not None
            assert agent.model_settings.reasoning.effort == "minimal"

    first_task = asyncio.create_task(first_run())
    await first_entered.wait()
    second_task = asyncio.create_task(second_run())
    await asyncio.sleep(0)

    assert not second_entered.is_set()
    assert agent.model_settings is not original_settings
    assert agent.model_settings.temperature is None

    release_first.set()
    await asyncio.gather(first_task, second_task)

    assert second_entered.is_set()
    assert agent.model_settings is original_settings
    assert agent.model_settings.temperature == 0.3
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "minimal"


@pytest.mark.parametrize("provider_model", ["openai/gpt-5.4-mini", "azure/gpt-5.4-mini"])
def test_agent_initialization_model_objects_use_openclaw_default_settings_alias(
    monkeypatch: pytest.MonkeyPatch,
    provider_model: str,
) -> None:
    monkeypatch.setenv("OPENCLAW_PROVIDER_MODEL", provider_model)
    model = build_openclaw_responses_model(base_url="http://127.0.0.1:18789/v1", api_key="test-key")

    agent = Agent(name="UsageTrackedModel", instructions="Test", model=model)

    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "none"
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


def test_agent_initialization_model_objects_without_default_settings_alias_keep_explicit_settings() -> None:
    class AnonymousModel(Model):
        async def get_response(
            self,
            system_instructions: str | None,
            input: str | list[TResponseInputItem],
            model_settings: ModelSettings,
            tools: list[Tool],
            output_schema: AgentOutputSchemaBase | None,
            handoffs: list[SDKHandoff],
            tracing: ModelTracing,
            *,
            previous_response_id: str | None,
            conversation_id: str | None,
            prompt: ResponsePromptParam | None,
        ) -> ModelResponse:
            raise AssertionError("Model execution is not part of this initialization test")

        def stream_response(
            self,
            system_instructions: str | None,
            input: str | list[TResponseInputItem],
            model_settings: ModelSettings,
            tools: list[Tool],
            output_schema: AgentOutputSchemaBase | None,
            handoffs: list[SDKHandoff],
            tracing: ModelTracing,
            *,
            previous_response_id: str | None,
            conversation_id: str | None,
            prompt: ResponsePromptParam | None,
        ) -> AsyncIterator[TResponseStreamEvent]:
            async def _stream() -> AsyncIterator[TResponseStreamEvent]:
                if False:
                    yield None
                return

            return _stream()

    agent = Agent(
        name="CustomModel",
        instructions="Test",
        model=AnonymousModel(),
        model_settings=ModelSettings(temperature=0.3, reasoning=Reasoning(effort="minimal")),
    )

    assert agent.model_settings.temperature == 0.3
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "minimal"
    assert agent.model_settings.truncation == "auto"


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


@pytest.mark.asyncio
async def test_agent_initialization_normalizes_direct_sdk_function_tool_manual_invocation() -> None:
    """Direct SDK FunctionTool inputs should support legacy manual invocation."""

    @sdk_function_tool
    def echo_name(name: str) -> str:
        return name

    agent = Agent(name="SdkTool", instructions="Test", tools=[echo_name])

    result = await agent.tools[0].on_invoke_tool(None, '{"name": "Ada"}')

    assert result == "Ada"


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

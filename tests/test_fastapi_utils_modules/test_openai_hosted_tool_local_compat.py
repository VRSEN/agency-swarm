import asyncio
from types import SimpleNamespace

import pytest


def _agency(agent: object) -> SimpleNamespace:
    return SimpleNamespace(agents={"A": agent})


@pytest.mark.parametrize("tool_kind", ["deferred", "namespaced", "custom"])
def test_non_openai_model_override_drops_unrelated_responses_only_tools(tool_kind: str) -> None:
    """Responses-only local tools should not reach Chat Completions-compatible conversion."""
    pytest.importorskip("agents")

    from agents import CustomTool, FunctionTool, ToolSearchTool, function_tool, tool_namespace
    from agents.models.chatcmpl_converter import Converter

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    async def invoke_replacement(_ctx: object, _input: str) -> str:
        return "replacement"

    if tool_kind == "deferred":

        @function_tool(defer_loading=True)
        def deferred_lookup() -> str:
            return "replacement"

        responses_only_tool = deferred_lookup
    elif tool_kind == "namespaced":

        @function_tool
        def namespaced_lookup() -> str:
            return "replacement"

        responses_only_tool = tool_namespace(
            name="lookup_namespace",
            description="Lookup namespace",
            tools=[namespaced_lookup],
        )[0]
    else:
        responses_only_tool = CustomTool(
            name="custom_lookup",
            description="Custom lookup",
            on_invoke_tool=invoke_replacement,
        )

    hosted = ToolSearchTool()
    agent = Agent(name="A", instructions="x", model="gpt-4o-mini", tools=[hosted, responses_only_tool])

    apply_openai_client_config(_agency(agent), ClientConfig(model="anthropic/claude-sonnet-4-6"))

    assert hosted not in agent.tools
    assert responses_only_tool not in agent.tools
    stubs = {tool.name: tool for tool in agent.tools if isinstance(tool, FunctionTool)}
    assert "tool_search" in stubs
    assert [Converter.tool_to_openai(tool)["function"]["name"] for tool in agent.tools] == ["tool_search"]


def test_non_openai_model_override_clears_tool_choice_for_dropped_responses_only_tool() -> None:
    """Forced tool choices should not point at tools removed for backend compatibility."""
    pytest.importorskip("agents")

    from agents import CustomTool, ModelSettings, ToolSearchTool

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    async def invoke_replacement(_ctx: object, _input: str) -> str:
        return "replacement"

    custom_tool = CustomTool(
        name="custom_lookup",
        description="Custom lookup",
        on_invoke_tool=invoke_replacement,
    )
    hosted = ToolSearchTool()
    agent = Agent(
        name="A",
        instructions="x",
        model="gpt-4o-mini",
        tools=[hosted, custom_tool],
        model_settings=ModelSettings(tool_choice="custom_lookup"),
    )

    apply_openai_client_config(_agency(agent), ClientConfig(model="anthropic/claude-sonnet-4-6"))

    assert custom_tool not in agent.tools
    assert agent.model_settings.tool_choice is None


def test_non_openai_model_override_stubs_local_shell_tool_instead_of_wrapping_executor() -> None:
    """LocalShellTool should not become a local FunctionTool replacement on non-OpenAI routes."""
    pytest.importorskip("agents")

    from unittest.mock import MagicMock

    from agents import FunctionTool, LocalShellTool

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    executor = MagicMock(return_value="executor-output")
    hosted = LocalShellTool(executor=executor)
    agent = Agent(name="A", instructions="x", model="gpt-4o-mini", tools=[hosted])

    apply_openai_client_config(_agency(agent), ClientConfig(model="anthropic/claude-sonnet-4-6"))

    assert hosted not in agent.tools
    stubs = {tool.name: tool for tool in agent.tools if isinstance(tool, FunctionTool)}
    assert "local_shell" in stubs
    assert "Unavailable hosted tool stub" in stubs["local_shell"].description
    assert "non-OpenAI backend" in asyncio.run(stubs["local_shell"].on_invoke_tool(None, "{}"))
    executor.assert_not_called()


def test_non_openai_model_override_stubs_shell_tool_instead_of_bypassing_approval() -> None:
    """ShellTool approval semantics should not be bypassed by wrapping the executor."""
    pytest.importorskip("agents")

    from unittest.mock import MagicMock

    from agents import FunctionTool, ShellTool

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    executor = MagicMock(return_value="executor-output")
    hosted = ShellTool(executor=executor, needs_approval=True)
    agent = Agent(name="A", instructions="x", model="gpt-4o-mini", tools=[hosted])

    apply_openai_client_config(_agency(agent), ClientConfig(model="anthropic/claude-sonnet-4-6"))

    assert hosted not in agent.tools
    stubs = {tool.name: tool for tool in agent.tools if isinstance(tool, FunctionTool)}
    assert "shell" in stubs
    assert "Unavailable hosted tool stub" in stubs["shell"].description
    assert "non-OpenAI backend" in asyncio.run(stubs["shell"].on_invoke_tool(None, "{}"))
    executor.assert_not_called()


def test_non_openai_model_override_stubs_hosted_container_shell_tool() -> None:
    """Hosted/container ShellTool should not be converted into local host shell execution."""
    pytest.importorskip("agents")

    from agents import FunctionTool, ShellTool

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    hosted = ShellTool(environment={"type": "container"})
    agent = Agent(name="A", instructions="x", model="gpt-4o-mini", tools=[hosted])

    apply_openai_client_config(_agency(agent), ClientConfig(model="anthropic/claude-sonnet-4-6"))

    assert hosted not in agent.tools
    stubs = {tool.name: tool for tool in agent.tools if isinstance(tool, FunctionTool)}
    assert "shell" in stubs
    assert "Unavailable hosted tool stub" in stubs["shell"].description
    assert "non-OpenAI backend" in asyncio.run(stubs["shell"].on_invoke_tool(None, "{}"))

import asyncio
from types import SimpleNamespace

import pytest


def _agency(agent: object) -> SimpleNamespace:
    return SimpleNamespace(agents={"A": agent})


@pytest.mark.parametrize(
    "model",
    [
        "litellm/ollama_chat/gemma4:e4b",
        "anthropic/claude-sonnet-4-6",
        "openrouter/anthropic/claude-sonnet-4.5",
        "openrouter/openai/gpt-5",
        "openclaw:main",
    ],
)
def test_non_openai_model_override_stubs_openai_hosted_tools(model: str) -> None:
    """Non-OpenAI request model overrides should replace OpenAI hosted tools with stubs."""
    pytest.importorskip("agents")

    from agents import FunctionTool, ToolSearchTool, WebSearchTool, function_tool

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    @function_tool
    def local_lookup() -> str:
        return "ok"

    hosted = WebSearchTool()
    tool_search = ToolSearchTool()
    agent = Agent(name="A", instructions="x", model="gpt-4o-mini", tools=[hosted, tool_search, local_lookup])
    agent.model_settings.response_include = [
        "web_search_call.action.sources",
        "file_search_call.results",
        "code_interpreter_call.outputs",
        "message.output_text.logprobs",
    ]
    config = (
        ClientConfig(model=model, api_key="sk-openrouter")
        if model.startswith("openrouter/")
        else ClientConfig(model=model)
    )

    apply_openai_client_config(_agency(agent), config)

    assert hosted not in agent.tools
    assert tool_search not in agent.tools
    stubs = {tool.name: tool for tool in agent.tools if isinstance(tool, FunctionTool)}
    assert {"web_search", "tool_search"} <= set(stubs)
    assert "non-OpenAI backend" in asyncio.run(stubs["web_search"].on_invoke_tool(None, "{}"))
    assert any(getattr(tool, "name", "") == "local_lookup" for tool in agent.tools)
    assert agent.model_settings.response_include == ["message.output_text.logprobs"]


def test_configured_openrouter_request_without_model_override_stubs_openai_hosted_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured OpenRouter agents should stub hosted tools for request-scoped gateway routes."""
    pytest.importorskip("agents")

    from agents import FunctionTool, ToolSearchTool, WebSearchTool, function_tool

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    @function_tool
    def local_lookup() -> str:
        return "ok"

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-original")
    hosted = WebSearchTool()
    tool_search = ToolSearchTool()
    agent = Agent(
        name="A",
        instructions="x",
        model="openrouter/anthropic/claude-sonnet-4.5",
        tools=[hosted, tool_search, local_lookup],
    )

    apply_openai_client_config(
        _agency(agent),
        ClientConfig(api_key="sk-openrouter", base_url="https://openrouter-proxy.test/v1"),
    )

    assert hosted not in agent.tools
    assert tool_search not in agent.tools
    stubs = {tool.name: tool for tool in agent.tools if isinstance(tool, FunctionTool)}
    assert {"web_search", "tool_search"} <= set(stubs)
    assert any(getattr(tool, "name", "") == "local_lookup" for tool in agent.tools)
    assert "web_search_call.action.sources" not in (agent.model_settings.response_include or [])


def test_non_openai_model_override_keeps_compatible_same_name_hosted_tool_replacement() -> None:
    """A compatible local replacement should prevent adding a duplicate hosted-tool stub."""
    pytest.importorskip("agents")

    from agents import FunctionTool, WebSearchTool, function_tool

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    @function_tool(name_override="web_search")
    def replacement_search() -> str:
        return "replacement"

    hosted = WebSearchTool()
    agent = Agent(name="A", instructions="x", model="gpt-4o-mini", tools=[hosted, replacement_search])

    apply_openai_client_config(_agency(agent), ClientConfig(model="anthropic/claude-sonnet-4-6"))

    assert hosted not in agent.tools
    web_search_tools = [tool for tool in agent.tools if isinstance(tool, FunctionTool) and tool.name == "web_search"]
    assert len(web_search_tools) == 1
    assert "Unavailable hosted tool stub" not in web_search_tools[0].description


@pytest.mark.parametrize("replacement", ["deferred", "namespaced", "custom"])
def test_non_openai_model_override_stubs_incompatible_same_name_hosted_tool_replacements(
    replacement: str,
) -> None:
    """Responses-only same-name local replacements should be replaced by a backend-safe stub."""
    pytest.importorskip("agents")

    from agents import CustomTool, FunctionTool, WebSearchTool, function_tool, tool_namespace
    from agents.models.chatcmpl_converter import Converter

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    async def invoke_replacement(_ctx: object, _input: str) -> str:
        return "replacement"

    if replacement == "deferred":

        @function_tool(name_override="web_search", defer_loading=True)
        def replacement_search() -> str:
            return "replacement"

        local_replacement = replacement_search
    elif replacement == "namespaced":

        @function_tool(name_override="web_search")
        def replacement_search() -> str:
            return "replacement"

        local_replacement = tool_namespace(
            name="search_namespace",
            description="Search namespace",
            tools=[replacement_search],
        )[0]
    else:
        local_replacement = CustomTool(
            name="web_search",
            description="Replacement custom search",
            on_invoke_tool=invoke_replacement,
        )

    hosted = WebSearchTool()
    agent = Agent(name="A", instructions="x", model="gpt-4o-mini", tools=[local_replacement, hosted])

    apply_openai_client_config(_agency(agent), ClientConfig(model="anthropic/claude-sonnet-4-6"))

    assert hosted not in agent.tools
    assert local_replacement not in agent.tools
    web_search_tools = [tool for tool in agent.tools if isinstance(tool, FunctionTool) and tool.name == "web_search"]
    assert len(web_search_tools) == 1
    assert "Unavailable hosted tool stub" in web_search_tools[0].description
    assert "non-OpenAI backend" in asyncio.run(web_search_tools[0].on_invoke_tool(None, "{}"))
    assert [Converter.tool_to_openai(tool)["function"]["name"] for tool in agent.tools] == ["web_search"]


@pytest.mark.parametrize("model", ["gpt-5", "openai/gpt-4o-mini"])
def test_openai_model_override_keeps_openai_hosted_tools(model: str) -> None:
    """OpenAI request model overrides should keep OpenAI hosted tools available."""
    pytest.importorskip("agents")

    from agents import ToolSearchTool, WebSearchTool

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    hosted = WebSearchTool()
    tool_search = ToolSearchTool()
    agent = Agent(name="A", instructions="x", model="gpt-4o-mini", tools=[hosted, tool_search])

    apply_openai_client_config(_agency(agent), ClientConfig(model=model))

    assert hosted in agent.tools
    assert tool_search in agent.tools
    assert "web_search_call.action.sources" in (agent.model_settings.response_include or [])


def test_openai_chat_completions_model_stubs_openai_hosted_tools() -> None:
    """OpenAI Chat Completions wrappers should not keep Responses-only hosted tools."""
    pytest.importorskip("agents")

    from agents import FunctionTool, OpenAIChatCompletionsModel, WebSearchTool
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    hosted = WebSearchTool()
    client = AsyncOpenAI(api_key="sk-openai")
    agent = Agent(
        name="A",
        instructions="x",
        model=OpenAIChatCompletionsModel(model="gpt-4o-mini", openai_client=client),
        tools=[hosted],
    )
    agent.model_settings.response_include = [
        "web_search_call.action.sources",
        "message.output_text.logprobs",
    ]

    apply_openai_client_config(_agency(agent), ClientConfig(model="gpt-4o-mini"))

    assert hosted not in agent.tools
    stubs = {tool.name: tool for tool in agent.tools if isinstance(tool, FunctionTool)}
    assert {"web_search"} <= set(stubs)
    assert agent.model_settings.response_include == ["message.output_text.logprobs"]


def test_snapshot_restore_preserves_tools_after_non_openai_model_override() -> None:
    """Request cleanup should restore hosted tools stubbed from non-OpenAI runs."""
    pytest.importorskip("agents")

    from agents import FunctionTool, ToolSearchTool, WebSearchTool, function_tool

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import (
        _restore_agency_state,
        _snapshot_agency_state,
        apply_openai_client_config,
    )
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    @function_tool
    def local_lookup() -> str:
        return "ok"

    hosted = WebSearchTool()
    tool_search = ToolSearchTool()
    agent = Agent(name="A", instructions="x", model="gpt-4o-mini", tools=[hosted, tool_search, local_lookup])
    original_tools = list(agent.tools)

    snapshot = _snapshot_agency_state(_agency(agent))
    apply_openai_client_config(_agency(agent), ClientConfig(model="litellm/ollama_chat/gemma4:e4b"))
    assert hosted not in agent.tools
    assert tool_search not in agent.tools
    assert {"web_search", "tool_search"} <= {tool.name for tool in agent.tools if isinstance(tool, FunctionTool)}
    assert agent.model_settings.response_include is None

    _restore_agency_state(_agency(agent), snapshot)

    assert agent.tools == original_tools
    assert agent.model_settings.response_include == ["web_search_call.action.sources"]


@pytest.mark.asyncio
async def test_response_endpoint_stubs_and_restores_hosted_tools_for_non_openai_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Request-scoped non-OpenAI model overrides should stub and restore hosted tools."""
    pytest.importorskip("agents")

    from agents import FunctionTool, ToolSearchTool, WebSearchTool, function_tool

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    @function_tool
    def local_lookup() -> str:
        return "ok"

    hosted = WebSearchTool()
    tool_search = ToolSearchTool()
    agent = Agent(name="A", instructions="x", model="gpt-4o-mini", tools=[hosted, tool_search, local_lookup])

    class _ThreadManager:
        def get_all_messages(self) -> list[object]:
            return []

    class _Response:
        final_output = "ok"

    class _Agency:
        def __init__(self) -> None:
            self.agents = {"A": agent}
            self.thread_manager = _ThreadManager()

        async def get_response(self, **_kwargs: object) -> _Response:
            tools = self.agents["A"].tools
            assert hosted not in tools
            assert tool_search not in tools
            assert {"web_search", "tool_search"} <= {tool.name for tool in tools if isinstance(tool, FunctionTool)}
            assert any(getattr(tool, "name", "") == "local_lookup" for tool in tools)
            assert self.agents["A"].model_settings.response_include is None
            return _Response()

    async def _attach_noop(_agency: _Agency) -> None:
        return None

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)

    agency = _Agency()
    handler = make_response_endpoint(BaseRequest, lambda **_: agency, verify_token=lambda: None)
    response = await handler(
        BaseRequest(
            message="hello",
            client_config=ClientConfig(model="litellm/ollama_chat/gemma4:e4b"),
        ),
        token=None,
    )

    assert response["response"] == "ok"
    assert hosted in agent.tools
    assert tool_search in agent.tools
    assert agent.model_settings.response_include == ["web_search_call.action.sources"]

from agents import (
    ApplyPatchTool,
    CodeInterpreterTool,
    ComputerTool,
    FileSearchTool,
    FunctionTool,
    HostedMCPTool,
    ImageGenerationTool,
    LocalShellTool,
    Model,
    OpenAIChatCompletionsModel,
    OpenAIResponsesModel,
    ShellTool,
    Tool,
    ToolSearchTool,
    WebSearchTool,
)

from agency_swarm.agent.core import Agent
from agency_swarm.utils.openrouter import get_openrouter_model_name

try:
    from agents.extensions.models.litellm_model import LitellmModel

    _LITELLM_AVAILABLE = True
except ImportError:
    _LITELLM_AVAILABLE = False
    LitellmModel = None  # type: ignore[misc, assignment]

_OPENAI_HOSTED_TOOL_TYPES = (
    FileSearchTool,
    WebSearchTool,
    ComputerTool,
    HostedMCPTool,
    ShellTool,
    ApplyPatchTool,
    LocalShellTool,
    ImageGenerationTool,
    CodeInterpreterTool,
    ToolSearchTool,
)
_OPENAI_HOSTED_RESPONSE_INCLUDES = frozenset(
    {
        "file_search_call.results",
        "web_search_call.results",
        "web_search_call.action.sources",
        "computer_call_output.output.image_url",
        "code_interpreter_call.outputs",
    }
)
type ToolSnapshot = list[Tool] | None


def restore_tool_snapshot(agent: Agent, tools: ToolSnapshot) -> None:
    if tools is not None:
        agent.tools = tools


def apply_openai_hosted_tool_compatibility(agent: Agent) -> None:
    if _supports_openai_hosted_tools(agent):
        return

    local_names = {
        name
        for tool in agent.tools
        if not isinstance(tool, _OPENAI_HOSTED_TOOL_TYPES)
        for name in [_tool_name(tool)]
        if name
    }
    stubbed: set[str] = set()
    tools: list[Tool] = []
    for tool in agent.tools:
        if not isinstance(tool, _OPENAI_HOSTED_TOOL_TYPES):
            tools.append(tool)
            continue
        name = _tool_name(tool)
        if not name or name in local_names or name in stubbed:
            continue
        tools.append(_build_unsupported_openai_hosted_tool_stub(name))
        stubbed.add(name)
    agent.tools = tools
    _strip_openai_hosted_response_includes(agent)


def _supports_openai_hosted_tools(agent: Agent) -> bool:
    if get_openrouter_model_name(agent.model) is not None:
        return False
    if _uses_litellm(agent):
        return False
    if isinstance(agent.model, OpenAIChatCompletionsModel):
        return False
    name = _request_model_name(agent)
    return bool(name) and _is_openai_model_name(name)


def _request_model_name(agent: Agent) -> str:
    model = agent.model
    if isinstance(model, str):
        name = model
    elif isinstance(model, OpenAIResponsesModel | OpenAIChatCompletionsModel):
        name = model.model
    elif _LITELLM_AVAILABLE and LitellmModel is not None and isinstance(model, LitellmModel):
        name = model.model
    elif isinstance(model, Model):
        name = getattr(model, "model", "")
    else:
        name = ""
    return name if isinstance(name, str) else ""


def _uses_litellm(agent: Agent) -> bool:
    model = agent.model
    if isinstance(model, str):
        return _is_litellm_model(model)
    if isinstance(model, OpenAIResponsesModel | OpenAIChatCompletionsModel):
        return _is_litellm_model(model.model)
    if _LITELLM_AVAILABLE and LitellmModel is not None and isinstance(model, LitellmModel):
        return True
    if isinstance(model, Model):
        name = getattr(model, "model", None)
        return isinstance(name, str) and _is_litellm_model(name)
    return False


def _is_litellm_model(name: str) -> bool:
    return name.startswith("litellm/")


def _is_openai_model_name(name: str) -> bool:
    if "/" not in name:
        return True
    prefix, _rest = name.split("/", 1)
    return prefix == "openai"


def _strip_openai_hosted_response_includes(agent: Agent) -> None:
    settings = getattr(agent, "model_settings", None)
    if settings is None or settings.response_include is None:
        return
    includes = [item for item in settings.response_include if item not in _OPENAI_HOSTED_RESPONSE_INCLUDES]
    settings.response_include = includes or None
    agent.model_settings = settings


def _tool_name(tool: Tool) -> str:
    name = getattr(tool, "name", "")
    return name if isinstance(name, str) else ""


def _build_unsupported_openai_hosted_tool_stub(name: str) -> FunctionTool:
    async def _invoke_stub(_ctx: object, _input: str) -> str:
        return f"The {name} hosted tool is unavailable because this request uses a non-OpenAI backend."

    return FunctionTool(
        name=name,
        description=f"Unavailable hosted tool stub for non-OpenAI backends: {name}.",
        params_json_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        },
        on_invoke_tool=_invoke_stub,
        strict_json_schema=False,
    )

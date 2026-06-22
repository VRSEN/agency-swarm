from typing import Protocol

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
    ModelSettings,
    OpenAIChatCompletionsModel,
    OpenAIResponsesModel,
    ShellTool,
    Tool,
    ToolSearchTool,
    WebSearchTool,
)
from agents.tool import get_function_tool_responses_only_features
from httpx import URL

from agency_swarm.messages.codex_input import is_codex_base_url
from agency_swarm.utils.openrouter import get_openrouter_model_name

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
_OPENAI_MODEL_NAME_PREFIXES = (
    "babbage-",
    "chatgpt-",
    "codex-",
    "computer-use-",
    "dall-e-",
    "davinci-",
    "ft:babbage-",
    "ft:chatgpt-",
    "ft:davinci-",
    "ft:gpt-",
    "ft:o1",
    "ft:o3",
    "ft:o4",
    "ft:o5",
    "gpt-",
    "o1",
    "o3",
    "o4",
    "o5",
    "omni-",
    "text-",
    "tts-",
    "whisper-",
)
_OPENAI_API_BASE_URL = "https://api.openai.com/v1"
_ATTACHMENT_COMPATIBILITY_ATTR = "_agency_swarm_apply_openai_hosted_tool_compatibility_after_attachments"
type ToolSnapshot = list[Tool] | None
type AttachmentCompatibilitySnapshot = bool | None


class ToolOwner(Protocol):
    model: str | Model | None
    tools: list[Tool]
    model_settings: ModelSettings


def restore_tool_snapshot(agent: ToolOwner, tools: ToolSnapshot) -> None:
    if tools is not None:
        agent.tools = tools


def snapshot_attachment_compatibility(agent: object) -> AttachmentCompatibilitySnapshot:
    enabled = getattr(agent, _ATTACHMENT_COMPATIBILITY_ATTR, None)
    return enabled if isinstance(enabled, bool) else None


def enable_attachment_compatibility(agent: object) -> None:
    setattr(agent, _ATTACHMENT_COMPATIBILITY_ATTR, True)


def restore_attachment_compatibility(agent: object, enabled: AttachmentCompatibilitySnapshot) -> None:
    if enabled is None:
        if hasattr(agent, _ATTACHMENT_COMPATIBILITY_ATTR):
            delattr(agent, _ATTACHMENT_COMPATIBILITY_ATTR)
        return
    setattr(agent, _ATTACHMENT_COMPATIBILITY_ATTR, enabled)


def apply_openai_hosted_tool_compatibility_after_attachment(agent: ToolOwner) -> None:
    if getattr(agent, _ATTACHMENT_COMPATIBILITY_ATTR, False) is True:
        apply_openai_hosted_tool_compatibility(agent)


def apply_openai_hosted_tool_compatibility(agent: ToolOwner) -> None:
    if _supports_openai_hosted_tools(agent):
        return

    hosted_names = {
        name
        for tool in agent.tools
        if isinstance(tool, _OPENAI_HOSTED_TOOL_TYPES)
        for name in [_tool_name(tool)]
        if name
    }
    local_names = {
        name
        for tool in agent.tools
        if not isinstance(tool, _OPENAI_HOSTED_TOOL_TYPES) and _is_non_responses_tool_compatible(tool)
        for name in [_tool_name(tool)]
        if name
    }
    stubbed: set[str] = set()
    tools: list[Tool] = []
    for tool in agent.tools:
        if not isinstance(tool, _OPENAI_HOSTED_TOOL_TYPES):
            if _tool_name(tool) in hosted_names and not _is_non_responses_tool_compatible(tool):
                continue
            tools.append(tool)
            continue
        name = _tool_name(tool)
        if not name or name in local_names or name in stubbed:
            continue
        tools.append(_build_unsupported_openai_hosted_tool_stub(name))
        stubbed.add(name)
    agent.tools = tools
    _strip_openai_hosted_response_includes(agent)


def _supports_openai_hosted_tools(agent: ToolOwner) -> bool:
    if get_openrouter_model_name(agent.model) is not None:
        return False
    if _uses_litellm(agent):
        return False
    if isinstance(agent.model, OpenAIChatCompletionsModel):
        return False
    if _uses_custom_openai_base_url(agent):
        return False
    name = _request_model_name(agent)
    return bool(name) and _is_openai_model_name(name)


def _request_model_name(agent: ToolOwner) -> str:
    model = agent.model
    if isinstance(model, str):
        name = model
    elif isinstance(model, OpenAIResponsesModel | OpenAIChatCompletionsModel):
        name = model.model
    elif _is_litellm_model_instance(model):
        name = getattr(model, "model", "")
    elif isinstance(model, Model):
        name = getattr(model, "model", "")
    else:
        name = ""
    return name if isinstance(name, str) else ""


def _uses_litellm(agent: ToolOwner) -> bool:
    model = agent.model
    if isinstance(model, str):
        return _is_litellm_model(model)
    if isinstance(model, OpenAIResponsesModel | OpenAIChatCompletionsModel):
        return _is_litellm_model(model.model)
    if _is_litellm_model_instance(model):
        return True
    if isinstance(model, Model):
        name = getattr(model, "model", None)
        return isinstance(name, str) and _is_litellm_model(name)
    return False


def _is_litellm_model(name: str) -> bool:
    return name.startswith("litellm/")


def _is_litellm_model_instance(model: object) -> bool:
    return any(
        cls.__module__ == "agents.extensions.models.litellm_model" and cls.__name__ == "LitellmModel"
        for cls in type(model).__mro__
    )


def _is_openai_model_name(name: str) -> bool:
    if "/" not in name:
        return name.startswith(_OPENAI_MODEL_NAME_PREFIXES)
    prefix, _rest = name.split("/", 1)
    return prefix == "openai"


def _uses_custom_openai_base_url(agent: ToolOwner) -> bool:
    model = agent.model
    if not isinstance(model, OpenAIResponsesModel | OpenAIChatCompletionsModel):
        return False
    client = getattr(model, "_client", None)
    base_url = getattr(client, "base_url", None)
    if base_url is None or is_codex_base_url(str(base_url)):
        return False
    return str(URL(str(base_url))).rstrip("/") != _OPENAI_API_BASE_URL


def _strip_openai_hosted_response_includes(agent: ToolOwner) -> None:
    settings = getattr(agent, "model_settings", None)
    if settings is None or settings.response_include is None:
        return
    includes = [item for item in settings.response_include if item not in _OPENAI_HOSTED_RESPONSE_INCLUDES]
    settings.response_include = includes or None
    agent.model_settings = settings


def _tool_name(tool: Tool) -> str:
    name = getattr(tool, "name", "")
    return name if isinstance(name, str) else ""


def _is_non_responses_tool_compatible(tool: Tool) -> bool:
    return isinstance(tool, FunctionTool) and not get_function_tool_responses_only_features(tool)


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

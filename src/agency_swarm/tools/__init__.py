import agents as _agents
from openai.types.responses import tool_param as _tool_param

from .base_tool import BaseTool
from .built_in import LoadFileAttachment, PersistentShellTool, PresentFiles
from .concurrency import ToolConcurrencyManager
from .function_tool_compat import function_tool
from .send_message import Handoff, SendMessage, SendMessageHandoff
from .tool_factory import ToolFactory
from .utils import (
    tool_output_file_from_file_id,
    tool_output_file_from_path,
    tool_output_file_from_url,
    tool_output_image_from_file_id,
    tool_output_image_from_path,
    validate_openapi_spec,
)

_SDK_TOOL_EXPORT_NAMES = {
    "AgentToolInvocation",
    "AgentToolStreamEvent",
    "ApplyPatchEditor",
    "ApplyPatchOperation",
    "ApplyPatchResult",
    "ApplyPatchTool",
    "AsyncComputer",
    "Button",
    "CodeInterpreterTool",
    "Computer",
    "ComputerProvider",
    "ComputerTool",
    "CustomTool",
    "Environment",
    "FileSearchTool",
    "FunctionTool",
    "FunctionToolResult",
    "HostedMCPTool",
    "ImageGenerationTool",
    "LocalShellCommandRequest",
    "LocalShellExecutor",
    "LocalShellTool",
    "MCPApprovalRequestItem",
    "MCPApprovalResponseItem",
    "MCPListToolsSpanData",
    "MCPToolApprovalFunction",
    "MCPToolApprovalFunctionResult",
    "MCPToolApprovalRequest",
    "ShellActionRequest",
    "ShellCallData",
    "ShellCallOutcome",
    "ShellCommandOutput",
    "ShellCommandRequest",
    "ShellExecutor",
    "ShellResult",
    "ShellTool",
    "ShellToolContainerAutoEnvironment",
    "ShellToolContainerNetworkPolicy",
    "ShellToolContainerNetworkPolicyAllowlist",
    "ShellToolContainerNetworkPolicyDisabled",
    "ShellToolContainerNetworkPolicyDomainSecret",
    "ShellToolContainerReferenceEnvironment",
    "ShellToolContainerSkill",
    "ShellToolEnvironment",
    "ShellToolHostedEnvironment",
    "ShellToolInlineSkill",
    "ShellToolInlineSkillSource",
    "ShellToolLocalEnvironment",
    "ShellToolLocalSkill",
    "ShellToolSkillReference",
    "StopAtTools",
    "Tool",
    "ToolApprovalItem",
    "ToolCallItem",
    "ToolCallOutputItem",
    "ToolErrorFormatter",
    "ToolErrorFormatterArgs",
    "ToolGuardrailFunctionOutput",
    "ToolInputGuardrail",
    "ToolInputGuardrailData",
    "ToolInputGuardrailResult",
    "ToolInputGuardrailTripwireTriggered",
    "ToolOrigin",
    "ToolOriginType",
    "ToolOutputFileContent",
    "ToolOutputFileContentDict",
    "ToolOutputGuardrail",
    "ToolOutputGuardrailData",
    "ToolOutputGuardrailResult",
    "ToolOutputGuardrailTripwireTriggered",
    "ToolOutputImage",
    "ToolOutputImageDict",
    "ToolOutputText",
    "ToolOutputTextDict",
    "ToolSearchTool",
    "ToolTimeoutError",
    "ToolsToFinalOutputFunction",
    "ToolsToFinalOutputResult",
    "WebSearchTool",
    "default_tool_error_function",
    "dispose_resolved_computers",
    "function_tool",
    "mcp_tools_span",
    "resolve_computer",
    "tool_input_guardrail",
    "tool_namespace",
    "tool_output_guardrail",
}
_SDK_TOOL_SHADOWED_EXPORTS = {"function_tool"}
for _sdk_name in _SDK_TOOL_EXPORT_NAMES:
    if _sdk_name not in _SDK_TOOL_SHADOWED_EXPORTS:
        if _sdk_name not in _agents.__all__:
            raise ImportError(f"Agents SDK export {_sdk_name!r} is not available")
        globals()[_sdk_name] = getattr(_agents, _sdk_name)

_TOOL_PARAM_IGNORED_EXPORTS = {
    "Dict",
    "Literal",
    "Optional",
    "Required",
    "SequenceNotStr",
    "TypeAlias",
    "TypedDict",
    "Union",
    "annotations",
}
_TOOL_PARAM_SHADOWED_EXPORTS = {"WebSearchTool"}
_TOOL_PARAM_EXPORT_NAMES = {
    name for name in dir(_tool_param) if not name.startswith("_") and name not in _TOOL_PARAM_IGNORED_EXPORTS
}
for _tool_param_name in _TOOL_PARAM_EXPORT_NAMES:
    if _tool_param_name not in _TOOL_PARAM_SHADOWED_EXPORTS:
        globals()[_tool_param_name] = getattr(_tool_param, _tool_param_name)

__all__ = [
    "BaseTool",
    "ToolFactory",
    "ToolConcurrencyManager",
    "SendMessage",
    "Handoff",
    "SendMessageHandoff",
    "validate_openapi_spec",
    "tool_output_image_from_path",
    "tool_output_image_from_file_id",
    "tool_output_file_from_path",
    "tool_output_file_from_url",
    "tool_output_file_from_file_id",
    # Re-exports from Agents SDK
    "CodeInterpreterTool",
    "ComputerTool",
    "FileSearchTool",
    "FunctionTool",
    "FunctionToolResult",
    "HostedMCPTool",
    "ImageGenerationTool",
    "LocalShellTool",
    "WebSearchTool",
    "function_tool",
    "ToolOutputText",
    "ToolOutputTextDict",
    "ToolOutputImage",
    "ToolOutputImageDict",
    "ToolOutputFileContent",
    "ToolOutputFileContentDict",
    # Built-in tools
    "LoadFileAttachment",
    "PresentFiles",
    "PersistentShellTool",
    "IPythonInterpreter",
    # Tool parameter types from OpenAI
    "CodeInterpreter",
    "CodeInterpreterContainer",
    "CodeInterpreterContainerCodeInterpreterToolAuto",
    "ImageGeneration",
    "ImageGenerationInputImageMask",
    "Mcp",
    "McpAllowedTools",
    "McpRequireApproval",
]
__all__.extend(
    name for name in sorted(_SDK_TOOL_EXPORT_NAMES) if name not in _SDK_TOOL_SHADOWED_EXPORTS and name not in __all__
)
__all__.extend(
    name
    for name in sorted(_TOOL_PARAM_EXPORT_NAMES)
    if name not in _TOOL_PARAM_SHADOWED_EXPORTS and name not in __all__
)


def __getattr__(name: str):
    """Lazy import for IPythonInterpreter to handle optional jupyter dependency."""
    if name == "IPythonInterpreter":
        from .built_in import IPythonInterpreter

        # Cache it in globals so subsequent access doesn't trigger __getattr__ again
        globals()[name] = IPythonInterpreter
        return IPythonInterpreter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

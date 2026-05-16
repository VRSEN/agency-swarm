import agents
from openai.types.responses import tool_param

import agency_swarm
import agency_swarm.tools as agency_tools

ROOT_SHADOWED_SDK_EXPORTS = {"Agent", "Handoff", "function_tool", "__version__"}
TOOLS_SHADOWED_SDK_EXPORTS = {"function_tool"}
EXPECTED_OPENAI_AGENTS_VERSION = "0.14.8"
EXPECTED_SDK_TOOL_EXPORTS = {
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
SDK_TOOL_EXPORT_REGRESSIONS = {
    "default_tool_error_function",
    "dispose_resolved_computers",
    "mcp_tools_span",
    "resolve_computer",
    "tool_input_guardrail",
    "tool_namespace",
    "tool_output_guardrail",
}
TOOL_PARAM_IGNORED_EXPORTS = {
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
TOOL_PARAM_SHADOWED_EXPORTS = {"WebSearchTool"}


def test_root_exports_agents_sdk_public_imports() -> None:
    expected_exports = set(agents.__all__) - ROOT_SHADOWED_SDK_EXPORTS

    missing_exports = sorted(expected_exports - set(agency_swarm.__all__))

    assert missing_exports == []
    assert agency_swarm.SDKAgent is agents.Agent
    assert agency_swarm.SDKHandoff is agents.Handoff
    assert agency_swarm.Agent is not agents.Agent
    assert agency_swarm.Handoff is not agents.Handoff
    for name in expected_exports:
        assert getattr(agency_swarm, name) is getattr(agents, name)


def test_tools_exports_agents_sdk_tool_imports() -> None:
    assert agents.__version__ == EXPECTED_OPENAI_AGENTS_VERSION
    expected_exports = EXPECTED_SDK_TOOL_EXPORTS - TOOLS_SHADOWED_SDK_EXPORTS

    missing_exports = sorted(expected_exports - set(agency_tools.__all__))

    assert missing_exports == []
    assert SDK_TOOL_EXPORT_REGRESSIONS <= set(agency_tools.__all__)
    for name in expected_exports:
        assert getattr(agency_tools, name) is getattr(agents, name)

    assert agency_tools.function_tool is not agents.function_tool


def test_tools_exports_openai_tool_param_imports() -> None:
    expected_exports = {
        name
        for name in dir(tool_param)
        if not name.startswith("_")
        and name not in TOOL_PARAM_IGNORED_EXPORTS
        and name not in TOOL_PARAM_SHADOWED_EXPORTS
    }

    missing_exports = sorted(expected_exports - set(agency_tools.__all__))

    assert missing_exports == []
    for name in expected_exports:
        assert getattr(agency_tools, name) is getattr(tool_param, name)

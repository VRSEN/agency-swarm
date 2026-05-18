import agents

import agency_swarm
import agency_swarm.tools as agency_tools

EXPECTED_OPENAI_AGENTS_VERSION = "0.14.8"

TOP_LEVEL_AGENTS_EXPORTS = {
    "AgentToolInvocation": "AgentToolInvocation",
    "CustomTool": "CustomTool",
    "ToolSearchTool": "ToolSearchTool",
    "ToolOrigin": "ToolOrigin",
    "ToolOriginType": "ToolOriginType",
    "ModelRetryAdvice": "ModelRetryAdvice",
    "ModelRetryAdviceRequest": "ModelRetryAdviceRequest",
    "ModelRetryBackoffSettings": "ModelRetryBackoffSettings",
    "ModelRetryNormalizedError": "ModelRetryNormalizedError",
    "ModelRetrySettings": "ModelRetrySettings",
    "OpenAIAgentRegistrationConfig": "OpenAIAgentRegistrationConfig",
    "OpenAIResponsesWSModel": "OpenAIResponsesWSModel",
    "ResponsesWebSocketSession": "ResponsesWebSocketSession",
    "RetryDecision": "RetryDecision",
    "RetryPolicy": "RetryPolicy",
    "RetryPolicyContext": "RetryPolicyContext",
    "RunConfig": "RunConfig",
    "Runner": "Runner",
    "SDKAgent": "Agent",
    "SDKHandoff": "Handoff",
    "TResponseInputItem": "TResponseInputItem",
    "Tool": "Tool",
    "flush_traces": "flush_traces",
    "responses_websocket_session": "responses_websocket_session",
    "retry_policies": "retry_policies",
    "sandbox": "sandbox",
    "set_default_openai_agent_registration": "set_default_openai_agent_registration",
    "set_default_openai_harness": "set_default_openai_harness",
    "set_default_openai_responses_transport": "set_default_openai_responses_transport",
    "tool_namespace": "tool_namespace",
}

TOOL_NAMESPACE_AGENTS_EXPORTS = {
    "Tool": "Tool",
    "CustomTool": "CustomTool",
    "ToolSearchTool": "ToolSearchTool",
    "ToolOrigin": "ToolOrigin",
    "ToolOriginType": "ToolOriginType",
    "tool_namespace": "tool_namespace",
}


def test_expected_openai_agents_version() -> None:
    assert agents.__version__ == EXPECTED_OPENAI_AGENTS_VERSION


def test_top_level_all_exports_resolve() -> None:
    for name in agency_swarm.__all__:
        assert hasattr(agency_swarm, name), name


def test_tools_module_all_exports_resolve() -> None:
    for name in agency_tools.__all__:
        assert hasattr(agency_tools, name), name


def test_top_level_explicit_agents_exports_match_sdk() -> None:
    for export_name, agents_name in TOP_LEVEL_AGENTS_EXPORTS.items():
        assert export_name in agency_swarm.__all__
        assert getattr(agency_swarm, export_name) is getattr(agents, agents_name)


def test_tools_module_explicit_tool_namespace_exports_match_sdk() -> None:
    for export_name, agents_name in TOOL_NAMESPACE_AGENTS_EXPORTS.items():
        assert export_name in agency_tools.__all__
        assert getattr(agency_tools, export_name) is getattr(agents, agents_name)


def test_agent_keeps_local_export_and_sdk_alias() -> None:
    assert agency_swarm.SDKAgent is agents.Agent
    assert agency_swarm.Agent is not agents.Agent
    assert "SDKAgent" in agency_swarm.__all__
    assert "Agent" in agency_swarm.__all__


def test_hosted_mcp_tool_exports_match_agents_sdk() -> None:
    assert agency_swarm.HostedMCPTool is agents.HostedMCPTool
    assert agency_tools.HostedMCPTool is agents.HostedMCPTool
    assert "HostedMCPTool" in agency_swarm.__all__
    assert "HostedMCPTool" in agency_tools.__all__


def test_image_generation_tool_exports_match_agents_sdk() -> None:
    assert agency_swarm.ImageGenerationTool is agents.ImageGenerationTool
    assert agency_tools.ImageGenerationTool is agents.ImageGenerationTool
    assert "ImageGenerationTool" in agency_swarm.__all__
    assert "ImageGenerationTool" in agency_tools.__all__


def test_function_tool_uses_agency_swarm_compat_wrapper() -> None:
    assert agency_swarm.function_tool is agency_tools.function_tool
    assert agency_swarm.function_tool is not agents.function_tool


def test_handoff_keeps_local_export_and_sdk_alias() -> None:
    assert agency_swarm.SDKHandoff is agents.Handoff
    assert agency_swarm.Handoff is agency_tools.Handoff
    assert agency_swarm.Handoff is not agents.Handoff

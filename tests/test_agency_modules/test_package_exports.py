import agents

import agency_swarm
import agency_swarm.tools as agency_tools

REQUIRED_TOP_LEVEL_AGENTS_EXPORTS = {
    "SDKAgent": "Agent",
    "SDKHandoff": "Handoff",
    "Runner": "Runner",
    "RunConfig": "RunConfig",
    "Tool": "Tool",
    "TResponseInputItem": "TResponseInputItem",
    "CustomTool": "CustomTool",
    "ToolSearchTool": "ToolSearchTool",
    "ToolOrigin": "ToolOrigin",
    "ToolOriginType": "ToolOriginType",
    "AgentToolInvocation": "AgentToolInvocation",
    "ModelProvider": "ModelProvider",
    "ModelTracing": "ModelTracing",
    "OpenAIResponsesModel": "OpenAIResponsesModel",
    "ImageGenerationTool": "ImageGenerationTool",
}

REQUIRED_TOOLS_AGENTS_EXPORTS = {
    "Tool": "Tool",
    "CustomTool": "CustomTool",
    "ToolSearchTool": "ToolSearchTool",
    "ToolOrigin": "ToolOrigin",
    "ToolOriginType": "ToolOriginType",
    "ImageGenerationTool": "ImageGenerationTool",
    "tool_namespace": "tool_namespace",
}


def test_all_declared_exports_resolve() -> None:
    for name in agency_swarm.__all__:
        assert hasattr(agency_swarm, name), name

    for name in agency_tools.__all__:
        assert hasattr(agency_tools, name), name


def test_top_level_required_agents_exports_match_sdk() -> None:
    for export_name, agents_name in REQUIRED_TOP_LEVEL_AGENTS_EXPORTS.items():
        assert export_name in agency_swarm.__all__
        assert getattr(agency_swarm, export_name) is getattr(agents, agents_name)


def test_tools_required_agents_exports_match_sdk() -> None:
    for export_name, agents_name in REQUIRED_TOOLS_AGENTS_EXPORTS.items():
        assert export_name in agency_tools.__all__
        assert getattr(agency_tools, export_name) is getattr(agents, agents_name)


def test_local_agent_and_handoff_keep_sdk_aliases() -> None:
    assert agency_swarm.SDKAgent is agents.Agent
    assert agency_swarm.Agent is not agents.Agent
    assert agency_swarm.SDKHandoff is agents.Handoff
    assert agency_swarm.Handoff is agency_tools.Handoff
    assert agency_swarm.Handoff is not agents.Handoff
    assert agency_swarm.function_tool is agency_tools.function_tool
    assert agency_swarm.function_tool is not agents.function_tool

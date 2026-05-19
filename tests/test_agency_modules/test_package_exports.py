import tomllib
from importlib.metadata import version
from pathlib import Path

import agents

import agency_swarm
import agency_swarm.tools as agency_tools

EXPECTED_AGENCY_SWARM_VERSION = "1.9.9"
EXPECTED_OPENAI_AGENTS_VERSION = "0.14.8"

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

NON_REQUIRED_TOP_LEVEL_EXPORTS = {
    "ModelRetryAdvice",
    "ModelRetryAdviceRequest",
    "ModelRetryBackoffSettings",
    "ModelRetryNormalizedError",
    "ModelRetrySettings",
    "OpenAIAgentRegistrationConfig",
    "OpenAIResponsesWSModel",
    "ResponsesWebSocketSession",
    "RetryDecision",
    "RetryPolicy",
    "RetryPolicyContext",
    "flush_traces",
    "responses_websocket_session",
    "retry_policies",
    "sandbox",
    "set_default_openai_agent_registration",
    "set_default_openai_harness",
    "set_default_openai_responses_transport",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_package_version_and_openai_agents_pin() -> None:
    project_data = tomllib.loads((_project_root() / "pyproject.toml").read_text())

    assert project_data["project"]["version"] == EXPECTED_AGENCY_SWARM_VERSION
    assert version("agency-swarm") == EXPECTED_AGENCY_SWARM_VERSION
    assert agents.__version__ == EXPECTED_OPENAI_AGENTS_VERSION
    assert f"openai-agents=={EXPECTED_OPENAI_AGENTS_VERSION}" in project_data["project"]["dependencies"]


def test_lockfile_keeps_openai_agents_pin() -> None:
    lock_data = tomllib.loads((_project_root() / "uv.lock").read_text())
    packages = {package["name"]: package for package in lock_data["package"]}

    assert packages["agency-swarm"]["version"] == EXPECTED_AGENCY_SWARM_VERSION
    assert packages["openai-agents"]["version"] == EXPECTED_OPENAI_AGENTS_VERSION
    assert {
        "name": "openai-agents",
        "specifier": f"=={EXPECTED_OPENAI_AGENTS_VERSION}",
    } in packages["agency-swarm"]["metadata"]["requires-dist"]


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


def test_non_required_sdk_internals_are_not_top_level_exports() -> None:
    assert sorted(NON_REQUIRED_TOP_LEVEL_EXPORTS & set(agency_swarm.__all__)) == []

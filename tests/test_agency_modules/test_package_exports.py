import agents

import agency_swarm
import agency_swarm.tools as agency_tools

EXPECTED_OPENAI_AGENTS_VERSION = "0.14.8"


def test_expected_openai_agents_version() -> None:
    assert agents.__version__ == EXPECTED_OPENAI_AGENTS_VERSION


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

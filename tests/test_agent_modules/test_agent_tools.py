"""Unit tests for agent tool validation."""

from typing import get_args, get_origin

import pytest
from agents import ComputerTool, FunctionTool, Tool

from agency_swarm.agent.tools import validate_hosted_tools, validate_tools
from agency_swarm.tools import BaseTool


def _hosted_tool_types() -> list[object]:
    hosted_tools: list[object] = []
    for tool_type in get_args(Tool):
        tool_class = get_origin(tool_type) or tool_type
        if tool_class is FunctionTool:
            continue
        hosted_tools.append(tool_type)
    return hosted_tools


def test_validate_hosted_tools_rejects_uninitialized_hosted_tool_classes() -> None:
    """All hosted tool classes must be instantiated before validation."""
    for tool_type in _hosted_tool_types():
        with pytest.raises(TypeError):
            validate_hosted_tools([tool_type])


def test_validate_tools_rejects_invalid_entries() -> None:
    """FunctionTool classes, invalid objects, and BaseTool instances should fail validation."""

    class SampleTool(BaseTool):
        def run(self) -> str:
            return "ok"

    invalid_cases: list[list[object]] = [
        [FunctionTool],
        [object()],
        [SampleTool()],
    ]
    for tools in invalid_cases:
        with pytest.raises(TypeError):
            validate_tools(tools)


def test_validate_tools_accepts_supported_entries() -> None:
    """BaseTool classes and initialized hosted tools should pass validation."""

    class SampleTool(BaseTool):
        def run(self) -> str:
            return "ok"

    validate_tools([SampleTool])
    validate_hosted_tools([ComputerTool(computer=object())])

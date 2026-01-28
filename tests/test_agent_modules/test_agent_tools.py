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


def _tool_type_id(tool_type: object) -> str:
    tool_class = get_origin(tool_type) or tool_type
    return getattr(tool_class, "__name__", str(tool_class))


@pytest.mark.parametrize("tool_type", _hosted_tool_types(), ids=_tool_type_id)
def test_validate_hosted_tools_rejects_uninitialized_hosted_tool_classes(tool_type: object) -> None:
    """Uninitialized hosted tool classes should raise TypeError."""
    with pytest.raises(TypeError):
        validate_hosted_tools([tool_type])


def test_validate_tools_rejects_uninitialized_function_tool_class() -> None:
    """Uninitialized FunctionTool classes should raise TypeError."""
    with pytest.raises(TypeError):
        validate_tools([FunctionTool])


def test_validate_tools_rejects_invalid_tool_object() -> None:
    """Invalid tool entries should raise TypeError."""
    with pytest.raises(TypeError):
        validate_tools([object()])


def test_validate_tools_rejects_basetool_instance() -> None:
    """BaseTool instances should raise TypeError."""

    class SampleTool(BaseTool):
        def run(self) -> str:
            return "ok"

    with pytest.raises(TypeError):
        validate_tools([SampleTool()])


def test_validate_tools_accepts_basetool_class() -> None:
    """BaseTool classes are valid Agent tool inputs and should be accepted."""

    class SampleTool(BaseTool):
        def run(self) -> str:
            return "ok"

    validate_tools([SampleTool])


def test_validate_hosted_tools_accepts_initialized_computer_tool() -> None:
    """Initialized hosted tool instances should pass validation."""
    tool = ComputerTool(computer=object())
    validate_hosted_tools([tool])

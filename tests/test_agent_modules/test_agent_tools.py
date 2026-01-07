"""Unit tests for agent tool validation."""

import pytest
from agents import ComputerTool

from agency_swarm.agent.tools import validate_hosted_tools


def test_validate_hosted_tools_rejects_uninitialized_computer_tool_class() -> None:
    """Uninitialized hosted tool classes should raise TypeError."""
    with pytest.raises(TypeError):
        validate_hosted_tools([ComputerTool])


def test_validate_hosted_tools_accepts_initialized_computer_tool() -> None:
    """Initialized hosted tool instances should pass validation."""
    tool = ComputerTool(computer=object())
    validate_hosted_tools([tool])

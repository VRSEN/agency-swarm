"""Safe replacements for OpenAI hosted tools on incompatible backends."""

from __future__ import annotations

import dataclasses

from agents import FunctionTool

from agency_swarm.tools.base_tool import BaseTool
from agency_swarm.tools.tool_factory import ToolFactory


def resolve_hosted_tool_replacement(name: str) -> FunctionTool | None:
    if name == "code_interpreter":
        return _build_code_interpreter_replacement()
    return None


def _adapt_base_tool_as(base_tool: type[BaseTool], name: str) -> FunctionTool:
    return dataclasses.replace(ToolFactory.adapt_base_tool(base_tool), name=name)


def _build_code_interpreter_replacement() -> FunctionTool | None:
    try:
        from agency_swarm.tools.built_in.IPythonInterpreter import IPythonInterpreter
    except ImportError:
        return None
    return _adapt_base_tool_as(IPythonInterpreter, "code_interpreter")

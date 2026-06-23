"""Default replacements for OpenAI hosted tools on incompatible backends."""

from __future__ import annotations

import dataclasses
from typing import Protocol

from agents import FunctionTool, Tool
from agents.mcp.server import MCPServer

from agency_swarm.tools.base_tool import BaseTool
from agency_swarm.tools.tool_factory import ToolFactory

EXA_MCP_BASE_URL = "https://mcp.exa.ai/mcp"
EXA_SEARCH_SERVER_NAME = "Exa_Search"
_EXA_ALLOWED_TOOL_NAMES = ("web_search_exa", "web_fetch_exa")
_BUILTIN_REPLACEMENT_TOOL_NAMES = frozenset({"web_search", "code_interpreter", "local_shell"})


class _McpServerOwner(Protocol):
    mcp_servers: list[MCPServer]


def has_builtin_hosted_tool_replacement(name: str) -> bool:
    return name in _BUILTIN_REPLACEMENT_TOOL_NAMES


def build_exa_search_server() -> MCPServer:
    from agents.mcp import MCPServerStreamableHttp

    return MCPServerStreamableHttp(
        name=EXA_SEARCH_SERVER_NAME,
        params={"url": EXA_MCP_BASE_URL},
        cache_tools_list=True,
        client_session_timeout_seconds=30,
        tool_filter={"allowed_tool_names": list(_EXA_ALLOWED_TOOL_NAMES)},
    )


def ensure_exa_search_server(agent: _McpServerOwner) -> None:
    if not isinstance(agent.mcp_servers, list):
        agent.mcp_servers = []
    servers = agent.mcp_servers
    if any(getattr(server, "name", None) == EXA_SEARCH_SERVER_NAME for server in servers):
        return
    servers.append(build_exa_search_server())


def has_exa_search_server(agent: object) -> bool:
    servers = getattr(agent, "mcp_servers", None)
    if not isinstance(servers, list):
        return False
    return any(getattr(server, "name", None) == EXA_SEARCH_SERVER_NAME for server in servers)


def _adapt_base_tool_as(base_tool: type[BaseTool], name: str) -> FunctionTool:
    return dataclasses.replace(ToolFactory.adapt_base_tool(base_tool), name=name)


def _build_code_interpreter_replacement() -> FunctionTool | None:
    try:
        from agency_swarm.tools.built_in.IPythonInterpreter import IPythonInterpreter
    except ImportError:
        return None
    return _adapt_base_tool_as(IPythonInterpreter, "code_interpreter")


def _build_local_shell_replacement() -> FunctionTool:
    from agency_swarm.tools.built_in.PersistentShellTool import PersistentShellTool

    return _adapt_base_tool_as(PersistentShellTool, "local_shell")


def resolve_hosted_tool_replacement(agent: _McpServerOwner, name: str) -> Tool | None:
    if name == "web_search":
        ensure_exa_search_server(agent)
        return None
    if name == "code_interpreter":
        return _build_code_interpreter_replacement()
    if name == "local_shell":
        return _build_local_shell_replacement()
    return None

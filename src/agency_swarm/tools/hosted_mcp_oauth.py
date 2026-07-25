from __future__ import annotations

from typing import Any

from agents import HostedMCPTool

_HOSTED_MCP_OAUTH_ENABLED_ATTR = "_agency_swarm_enable_hosted_mcp_oauth"


def enable_hosted_mcp_tool_oauth(tool: HostedMCPTool) -> HostedMCPTool:
    """Mark a HostedMCPTool for Agency Swarm's FastAPI OAuth flow.

    This opt-in is used only by the FastAPI integration. `run_fastapi(...)`
    creates an in-memory callback-state registry by default. An external
    `oauth_registry` shares callback state across workers, but token storage
    also needs shared persistent storage or sticky routing. This does not
    change the non-FastAPI hosted MCP authorization path.
    """
    setattr(tool, _HOSTED_MCP_OAUTH_ENABLED_ATTR, True)
    return tool


def is_hosted_mcp_tool_oauth_enabled(tool: Any) -> bool:
    """Return True when a HostedMCPTool explicitly opts into FastAPI OAuth."""
    return bool(getattr(tool, _HOSTED_MCP_OAUTH_ENABLED_ATTR, False))

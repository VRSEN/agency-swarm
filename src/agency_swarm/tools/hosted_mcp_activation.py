"""Deferred OAuth activation for hosted MCP tools.

Withholds opted-in ``HostedMCPTool`` definitions until the model asks to authenticate,
then injects a request-local clone carrying the OAuth access token.
"""

import copy
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from agency_swarm.tools.hosted_mcp_oauth import (
    enable_hosted_mcp_tool_oauth,
    is_hosted_mcp_tool_oauth_enabled,
)
from agency_swarm.tools.mcp_oauth_bridge import (
    _OAUTH_AVAILABLE,
    OAuthHandlerMap,
    _MCPServerOAuth,
    _MCPServerOAuthClient,
    apply_managed_oauth_cache_dir,
)

_HostedMCPTool: type[Any] | None
try:
    from agents.tool import HostedMCPTool as _HostedMCPTool
except ImportError:  # pragma: no cover - compatibility with older Agents SDKs
    _HostedMCPTool = None

if TYPE_CHECKING:
    from agency_swarm.mcp.oauth import MCPServerOAuth

_HOSTED_MCP_OAUTH_ORIGINAL_TOOL_ATTR = "_agency_swarm_hosted_mcp_oauth_original_tool"
_HOSTED_MCP_OAUTH_ORIGINAL_TOOLS_ATTR = "_agency_swarm_hosted_mcp_oauth_original_tools"
_HOSTED_MCP_OAUTH_ACTIVATION_HANDLER_ATTR = "_agency_swarm_hosted_mcp_oauth_activation_handler"


async def _authorize_hosted_mcp_tool(agent: Any, source_tool: Any, *, cache_dir: Path | None) -> Any | None:
    """Return a request-local HostedMCPTool with an OAuth access token."""
    if not _OAUTH_AVAILABLE or _MCPServerOAuth is None or _MCPServerOAuthClient is None:
        return None
    if _HostedMCPTool is None:
        return None
    source_tool_config = getattr(source_tool, "tool_config", None)
    if not isinstance(source_tool_config, dict):
        return None
    server_label = source_tool_config.get("server_label")
    server_url = source_tool_config.get("server_url")
    if not isinstance(server_label, str) or server_label == "":
        return None
    if not isinstance(server_url, str) or server_url == "":
        return None

    active_tool = enable_hosted_mcp_tool_oauth(
        _HostedMCPTool(
            tool_config=cast(dict[str, Any], dict(source_tool_config)),
            on_approval_request=getattr(source_tool, "on_approval_request", None),
        )
    )
    setattr(active_tool, _HOSTED_MCP_OAUTH_ORIGINAL_TOOL_ATTR, source_tool)
    active_tool_config = cast(dict[str, Any], active_tool.tool_config)
    handler_factory = getattr(agent, "mcp_oauth_handler_factory", None)
    factory: Callable[[str], OAuthHandlerMap] | None = None
    if callable(handler_factory):
        factory = cast("Callable[[str], OAuthHandlerMap]", handler_factory)

    oauth_config_type = cast("type[MCPServerOAuth]", _MCPServerOAuth)
    oauth_client_type = cast(type[Any], _MCPServerOAuthClient)
    oauth_srv = oauth_config_type(url=server_url, name=server_label, use_env_credentials=False)
    apply_managed_oauth_cache_dir(oauth_srv, cache_dir)
    server_handlers: OAuthHandlerMap = {}
    if factory is not None:
        server_handlers.update(factory(server_label))
    oauth_client = oauth_client_type(oauth_srv, server_handlers or None)

    try:
        await oauth_client.connect()
        provider = getattr(oauth_client, "_oauth_provider", None)
        if provider is None:
            return None
        tokens = await provider.context.storage.get_tokens()
        if tokens is None or not getattr(tokens, "access_token", None):
            return None
        active_tool_config["authorization"] = tokens.access_token
        return active_tool
    finally:
        await oauth_client.cleanup()


def _stage_deferred_hosted_mcp_tools(agent: Any, *, cache_dir: Path | None) -> None:
    """Withhold opted-in hosted tools until the model requests OAuth activation."""
    tools = getattr(agent, "tools", None)
    if not isinstance(tools, list) or getattr(agent, "_hosted_mcp_oauth_enabled", False) is not True:
        return
    if isinstance(getattr(agent, _HOSTED_MCP_OAUTH_ORIGINAL_TOOLS_ATTR, None), list):
        return

    candidates: dict[str, Any] = {}
    for tool in tools:
        if getattr(tool, "name", None) != "hosted_mcp" or not is_hosted_mcp_tool_oauth_enabled(tool):
            continue
        tool_config = getattr(tool, "tool_config", None)
        if not isinstance(tool_config, dict) or tool_config.get("authorization") not in (None, ""):
            continue
        server_label = tool_config.get("server_label")
        server_url = tool_config.get("server_url")
        if not isinstance(server_label, str) or server_label == "":
            continue
        if not isinstance(server_url, str) or server_url == "":
            continue
        if server_label in candidates:
            raise ValueError(f"Hosted MCP server name '{server_label}' must be unique for OAuth activation")
        candidates[server_label] = tool
    if not candidates:
        return

    local_servers = getattr(agent, "_oauth_mcp_servers", {})
    local_names = set(local_servers) if isinstance(local_servers, dict) else set()
    conflicts = local_names.intersection(candidates)
    if conflicts:
        conflict = sorted(conflicts)[0]
        raise ValueError(f"MCP server name '{conflict}' is duplicated across local and hosted OAuth tools")

    async def _activate_hosted_mcp(server_name: str) -> str | None:
        selected = candidates.get(server_name)
        if selected is None:
            return None
        active_tool = await _authorize_hosted_mcp_tool(agent, selected, cache_dir=cache_dir)
        if active_tool is None:
            return f"Failed to authenticate MCP server '{server_name}': no OAuth access token was returned"

        current_tools = list(getattr(agent, "tools", []))
        for index, tool in enumerate(current_tools):
            if getattr(tool, _HOSTED_MCP_OAUTH_ORIGINAL_TOOL_ATTR, None) is selected:
                current_tools[index] = active_tool
                break
        else:
            current_tools.append(active_tool)
        agent.tools = current_tools
        return f"MCP server '{server_name}' is authenticated and its tools are enabled."

    installer = getattr(agent, "_install_mcp_authentication_tool", None)
    if not callable(installer):
        return
    original_tools = tools
    activation_tool = next((tool for tool in tools if getattr(tool, "name", None) == "authenticate_mcp_server"), None)
    original_schema = copy.deepcopy(getattr(activation_tool, "params_json_schema", None))
    agent.tools = list(tools)
    try:
        installer(sorted(local_names.union(candidates)))
    except BaseException:
        agent.tools = original_tools
        raise
    if activation_tool is not None and isinstance(original_schema, dict):
        request_schema = copy.deepcopy(activation_tool.params_json_schema)
        activation_tool.params_json_schema = original_schema
        request_activation = copy.copy(activation_tool)
        request_activation.params_json_schema = request_schema
        agent.tools = [request_activation if tool is activation_tool else tool for tool in agent.tools]
    setattr(agent, _HOSTED_MCP_OAUTH_ORIGINAL_TOOLS_ATTR, original_tools)
    setattr(agent, _HOSTED_MCP_OAUTH_ACTIVATION_HANDLER_ATTR, _activate_hosted_mcp)
    withheld = {id(tool) for tool in candidates.values()}
    agent.tools = [tool for tool in agent.tools if id(tool) not in withheld]


def restore_hosted_mcp_oauth_tools(agency: Any) -> None:
    """Restore HostedMCPTool definitions replaced by request-scoped OAuth injection."""
    agents_map = getattr(agency, "agents", None)
    if not isinstance(agents_map, dict):
        return
    for agent in agents_map.values():
        tools = getattr(agent, "tools", None)
        if not isinstance(tools, list):
            continue
        original_tools = getattr(agent, _HOSTED_MCP_OAUTH_ORIGINAL_TOOLS_ATTR, None)
        if not isinstance(original_tools, list):
            continue
        agent.tools = original_tools
        delattr(agent, _HOSTED_MCP_OAUTH_ORIGINAL_TOOLS_ATTR)
        if hasattr(agent, _HOSTED_MCP_OAUTH_ACTIVATION_HANDLER_ATTR):
            delattr(agent, _HOSTED_MCP_OAUTH_ACTIVATION_HANDLER_ATTR)

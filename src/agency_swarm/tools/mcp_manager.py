"""Entry points that bind an agent's or agency's MCP servers to the persistent manager.

The registry itself lives in :mod:`agency_swarm.tools.mcp_persistence`, the loop-affine
proxy in :mod:`agency_swarm.tools.mcp_loop_proxy`, the optional OAuth wiring in
:mod:`agency_swarm.tools.mcp_oauth_bridge`, and hosted MCP OAuth activation in
:mod:`agency_swarm.tools.hosted_mcp_activation`. All of their names are re-exported here
so ``from agency_swarm.tools.mcp_manager import X`` keeps working unchanged.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from agents import FunctionTool

from agency_swarm.mcp.oauth_user import build_oauth_user_segment  # noqa: F401
from agency_swarm.tools.hosted_mcp_activation import (
    _HOSTED_MCP_OAUTH_ACTIVATION_HANDLER_ATTR,  # noqa: F401
    _HOSTED_MCP_OAUTH_ORIGINAL_TOOL_ATTR,  # noqa: F401
    _HOSTED_MCP_OAUTH_ORIGINAL_TOOLS_ATTR,  # noqa: F401
    _authorize_hosted_mcp_tool,  # noqa: F401
    _HostedMCPTool,  # noqa: F401
    _stage_deferred_hosted_mcp_tools,
    restore_hosted_mcp_oauth_tools,  # noqa: F401
)
from agency_swarm.tools.hosted_mcp_oauth import (
    enable_hosted_mcp_tool_oauth,  # noqa: F401
    is_hosted_mcp_tool_oauth_enabled,  # noqa: F401
)
from agency_swarm.tools.mcp_loop_proxy import LoopAffineAsyncProxy
from agency_swarm.tools.mcp_oauth_bridge import (
    _MANAGED_OAUTH_CACHE_DIR_ATTR,  # noqa: F401
    _OAUTH_AVAILABLE,
    OAuthCallbackHandler,  # noqa: F401
    OAuthHandlerMap,  # noqa: F401
    OAuthRedirectHandler,  # noqa: F401
    _build_persistence_key,
    _clone_oauth_candidate,
    _create_oauth_provider,  # noqa: F401
    _current_oauth_handlers,  # noqa: F401
    _get_oauth_runtime_context,
    _get_oauth_user_id,
    _MCPServerOAuth,  # noqa: F401
    _MCPServerOAuthClient,  # noqa: F401
    _oauth_endpoint_key_segment,  # noqa: F401
    _oauth_request_key_suffix,
    _oauth_store_key_segment,  # noqa: F401
    _process_oauth_servers,
    _sanitize_oauth_registry_user_id,  # noqa: F401
    _set_oauth_runtime_context,  # noqa: F401
    _set_oauth_user_id,  # noqa: F401
    _sync_oauth_client_handlers,
    apply_managed_oauth_cache_dir,  # noqa: F401
    bind_managed_oauth_cache_dir,  # noqa: F401
    get_active_oauth_user_id,  # noqa: F401
)
from agency_swarm.tools.mcp_persistence import (
    _OAUTH_LIST_TOOLS_TIMEOUT_GRACE_SECONDS,  # noqa: F401
    _OAUTH_LIST_TOOLS_TIMEOUT_SECONDS,  # noqa: F401
    PersistentMCPServerManager,
)

if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent


default_mcp_manager = PersistentMCPServerManager()


async def attach_persistent_mcp_servers(agency: Any) -> None:
    """Attach and connect persistent MCP servers to all agents in an agency.

    - Replaces each agent's server with a shared instance keyed by `server.name`.
    - Connects servers once (if not already connected).
    - No-ops for servers without a `name` attribute.
    """
    agents_map = getattr(agency, "agents", None)
    if not isinstance(agents_map, dict):
        return
    cache_dir: Path | None = None
    oauth_token_path = getattr(agency, "oauth_token_path", None)
    if isinstance(oauth_token_path, str) and oauth_token_path != "":
        cache_dir = Path(oauth_token_path).expanduser()
    oauth_user_id = _get_oauth_user_id() if _get_oauth_user_id is not None else None
    for agent in agents_map.values():
        ensure_mcp_tools = getattr(agent, "ensure_mcp_tools", None)
        if callable(ensure_mcp_tools):
            ensure_mcp_tools()
        _stage_deferred_hosted_mcp_tools(agent, cache_dir=cache_dir)
        servers = getattr(agent, "mcp_servers", None)
        if not isinstance(servers, list):
            continue
        if _OAUTH_AVAILABLE:
            _process_oauth_servers(agent, servers)
        for i, srv in enumerate(list(servers)):
            name = getattr(srv, "name", None)
            if not isinstance(name, str) or name == "":
                raise ValueError(f"Server {srv} has no name provided")

            candidate = _clone_oauth_candidate(srv)
            key = _build_persistence_key(candidate, oauth_user_id)
            if key == "":
                raise ValueError(f"Server {srv} has no valid persistence key")

            persistent = default_mcp_manager.get(key)
            if persistent is None:
                persistent = default_mcp_manager.register(candidate, key=key)
            else:
                _sync_oauth_client_handlers(persistent, candidate)
            # Replace the reference so future runs reuse the same object and ensure loop‑affine proxy
            replacement = (
                persistent
                if isinstance(persistent, LoopAffineAsyncProxy)
                else LoopAffineAsyncProxy(persistent, default_mcp_manager)
            )
            if replacement is not servers[i]:
                servers[i] = replacement
        # After replacing, ensure all are connected once
        for srv in servers:
            await default_mcp_manager.ensure_connected(srv)


async def cleanup_oauth_runtime_mcp_servers() -> None:
    """Remove request-scoped OAuth MCP clients for the active runtime context."""
    runtime_context = _get_oauth_runtime_context() if _get_oauth_runtime_context is not None else None
    request_id = getattr(runtime_context, "request_id", None) if runtime_context is not None else None
    if getattr(runtime_context, "mode", None) != "saas_stream" or not isinstance(request_id, str):
        return
    await default_mcp_manager.unregister_keys_ending_with(_oauth_request_key_suffix(request_id))


def register_and_connect_agent_servers(agent: Any) -> None:
    """Register an agent's MCP servers in the persistent manager and connect them.

    This is a synchronous facade that safely handles both sync and async contexts:
    - If an event loop is running, schedules an async task to connect servers.
    - Otherwise, creates a temporary loop to connect synchronously.
    - Supports OAuth-enabled servers via MCPServerOAuth instances.
    """
    servers = getattr(agent, "mcp_servers", None)
    if not isinstance(servers, list) or len(servers) == 0:
        return

    # Process OAuth servers first
    if _OAUTH_AVAILABLE:
        _process_oauth_servers(agent, servers)

    server_names = []
    oauth_user_id = _get_oauth_user_id() if _get_oauth_user_id is not None else None
    # Replace each server with the persistent instance (by name) if available
    for i, srv in enumerate(list(servers)):
        name = getattr(srv, "name", None)
        if isinstance(name, str) and name != "" and name not in server_names:
            server_names.append(name)
            candidate = _clone_oauth_candidate(srv)
            key = _build_persistence_key(candidate, oauth_user_id)
            persistent = default_mcp_manager.get(key) or default_mcp_manager.register(candidate, key=key)
            if persistent is not candidate:
                _sync_oauth_client_handlers(persistent, candidate)
            if persistent is not servers[i]:
                servers[i] = persistent
        elif name in server_names:
            raise ValueError(
                f"Server {srv} has duplicate name: {name}. "
                "Please provide server with unique names by explicitly specifying the name attribute."
            )
        else:
            raise ValueError(f"Server {srv} has no name provided")

    # Establish connections during Agent init and bind all ops to background loop
    for idx, srv in enumerate(list(servers)):
        # Always use loop‑affine proxy for MCP servers
        if not isinstance(srv, LoopAffineAsyncProxy):
            proxy = LoopAffineAsyncProxy(srv, default_mcp_manager)
            servers[idx] = proxy
            srv = proxy

        # Ensure driver is created and connected on the background loop (synchronous)
        default_mcp_manager._ensure_driver(getattr(srv, "_server", srv))


def convert_mcp_servers_to_tools(agent: "Agent", *, add_to_agent: bool = True) -> list[FunctionTool]:
    """Convert agent's MCP servers to FunctionTool instances and add them to the agent's tools.

    This function:
    1. Converts all MCP servers to FunctionTool instances using ToolFactory.from_mcp
    2. Adds the converted tools to the agent's tools list when requested
    3. Clears the agent's mcp_servers list

    Args:
        agent: The agent instance to process
    """
    from agency_swarm.tools.tool_factory import ToolFactory

    servers = getattr(agent, "mcp_servers", None)
    if not isinstance(servers, list) or len(servers) == 0:
        return []

    if _OAUTH_AVAILABLE:
        _process_oauth_servers(agent, servers)

    # Read convert_schemas_to_strict from agent's mcp_config
    mcp_config = getattr(agent, "mcp_config", None) or {}
    convert_to_strict = mcp_config.get("convert_schemas_to_strict", False)

    # Convert MCP servers to FunctionTool instances
    converted_tools = ToolFactory.from_mcp(
        servers,
        convert_schemas_to_strict=convert_to_strict,
        context=None,
        agent=agent,
    )
    if add_to_agent:
        for tool in converted_tools:
            agent.add_tool(tool)

    # Clear the mcp_servers list
    agent.mcp_servers.clear()
    return converted_tools

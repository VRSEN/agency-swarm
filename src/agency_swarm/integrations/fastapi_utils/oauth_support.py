import asyncio
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse

MCPServerOAuthRuntime: type[Any] | None
MCPServerOAuthClientRuntime: type[Any] | None
HostedMCPToolRuntime: type[Any] | None

try:
    from agency_swarm.mcp.oauth import MCPServerOAuth as MCPServerOAuthRuntime
    from agency_swarm.mcp.oauth_client import MCPServerOAuthClient as MCPServerOAuthClientRuntime
except ImportError:  # pragma: no cover - optional dependency
    MCPServerOAuthRuntime = None
    MCPServerOAuthClientRuntime = None

try:
    from agents.tool import HostedMCPTool as HostedMCPToolRuntime
except ImportError:  # pragma: no cover - agents sdk is an optional dependency
    HostedMCPToolRuntime = None


class OAuthFlowError(Exception):
    """Raised when an OAuth flow cannot complete."""


@dataclass
class OAuthFlowState:
    """Holds per-state OAuth flow metadata."""

    state: str
    auth_url: str
    server_name: str | None
    user_id: str | None
    code: str | None = None
    error: str | None = None
    status: str = "pending"
    event: asyncio.Event = field(default_factory=asyncio.Event)
    created_at: float = field(default_factory=time.time)


class OAuthStateRegistry:
    """In-memory registry coordinating OAuth redirects and callbacks."""

    def __init__(self, *, expiry_seconds: float | None = 900.0) -> None:
        self._flows: dict[str, OAuthFlowState] = {}
        self._lock = asyncio.Lock()
        self._expiry_seconds = expiry_seconds

    def _prune_expired_locked(self) -> None:
        """Remove expired flows to avoid unbounded growth."""
        if self._expiry_seconds is None:
            return
        cutoff = time.time() - self._expiry_seconds
        expired = [state for state, flow in self._flows.items() if flow.created_at < cutoff]
        for state in expired:
            self._flows.pop(state, None)

    async def record_redirect(
        self,
        *,
        state: str,
        auth_url: str,
        server_name: str | None,
        user_id: str | None,
    ) -> OAuthFlowState:
        """Store redirect details and return the flow state."""
        async with self._lock:
            self._prune_expired_locked()
            flow = self._flows.get(state)
            if flow is None:
                flow = OAuthFlowState(state=state, auth_url=auth_url, server_name=server_name, user_id=user_id)
                self._flows[state] = flow
            else:
                flow.auth_url = auth_url
                flow.server_name = server_name
                flow.user_id = user_id or flow.user_id
                flow.error = None
                flow.code = None
                flow.status = "pending"
            return flow

    async def set_code(self, *, state: str, code: str, user_id: str | None) -> OAuthFlowState:
        """Persist the authorization code and release any waiters."""
        async with self._lock:
            self._prune_expired_locked()
            flow = self._flows.get(state)
            if flow is None:
                flow = OAuthFlowState(state=state, auth_url="", server_name=None, user_id=user_id, code=code)
                self._flows[state] = flow
            else:
                if flow.user_id and user_id and flow.user_id != user_id:
                    flow.error = "user_mismatch"
                    flow.status = "error:user_mismatch"
                else:
                    flow.status = "authorized"
                flow.code = code
            flow.event.set()
            return flow

    async def set_error(self, *, state: str, error: str, error_description: str | None = None) -> OAuthFlowState:
        """Persist an OAuth provider error and release any waiters."""
        async with self._lock:
            self._prune_expired_locked()
            flow = self._flows.get(state)
            error_msg = f"{error}: {error_description}" if error_description else error
            if flow is None:
                flow = OAuthFlowState(state=state, auth_url="", server_name=None, user_id=None, error=error_msg)
                self._flows[state] = flow
            else:
                flow.error = error_msg
            flow.status = f"error:{error_msg}"
            flow.event.set()
            return flow

    async def set_timeout(self, *, state: str) -> OAuthFlowState:
        """Mark an OAuth flow as timed out and release any waiters."""
        async with self._lock:
            self._prune_expired_locked()
            flow = self._flows.get(state)
            if flow is None:
                flow = OAuthFlowState(state=state, auth_url="", server_name=None, user_id=None)
                self._flows[state] = flow
            flow.status = "timeout"
            flow.error = None
            flow.event.set()
            return flow

    async def wait_for_code(self, *, state: str, timeout: float | None = 300.0) -> tuple[str, str | None]:
        """Wait for the callback to supply an authorization code."""
        flow = await self._get_or_raise(state)
        try:
            await asyncio.wait_for(flow.event.wait(), timeout=timeout)
        except TimeoutError as exc:  # pragma: no cover - timeout exercised in runtime paths
            await self.set_timeout(state=state)
            raise OAuthFlowError(f"Timed out waiting for OAuth callback for state={state}") from exc

        if flow.error:
            raise OAuthFlowError(flow.error)
        if not flow.code:
            raise OAuthFlowError(f"OAuth callback missing code for state={state}")
        async with self._lock:
            self._prune_expired_locked()
        return flow.code, flow.state

    async def get_status(self, state: str) -> dict[str, Any]:
        """Return a serializable snapshot for status endpoint."""
        async with self._lock:
            self._prune_expired_locked()
            flow = self._flows.get(state)
            if flow is None:
                return {"state": state, "status": "unknown"}
            return {
                "state": state,
                "status": flow.status,
                "auth_url": flow.auth_url,
                "server_name": flow.server_name,
                "user_id": flow.user_id,
            }

    async def _get_or_raise(self, state: str) -> OAuthFlowState:
        async with self._lock:
            self._prune_expired_locked()
            if state not in self._flows:
                raise OAuthFlowError(f"No OAuth flow registered for state={state}")
            return self._flows[state]


def extract_state_from_url(auth_url: str) -> str:
    """Extract the OAuth state parameter from an authorization URL."""
    parsed = urlparse(auth_url)
    params = parse_qs(parsed.query)
    if "state" not in params or not params["state"]:
        raise OAuthFlowError("OAuth redirect URL missing state parameter")
    return params["state"][0]


def is_oauth_server(server: Any) -> bool:
    """Return True when the object is an OAuth MCP config or client."""
    if MCPServerOAuthRuntime is not None and isinstance(server, MCPServerOAuthRuntime):
        return True
    if MCPServerOAuthClientRuntime is not None and isinstance(server, MCPServerOAuthClientRuntime):
        return True
    return False


def has_hosted_mcp_tools_missing_authorization(agency_instance: Any) -> bool:
    """Return True when HostedMCPTool is present without an access token.

    Hosted MCP tools require the caller to supply an OAuth access token via
    `tool_config.authorization` when the remote server is OAuth-protected.
    """
    if HostedMCPToolRuntime is None:
        return False
    agents_map = getattr(agency_instance, "agents", {})
    if not isinstance(agents_map, dict):
        return False
    for agent in agents_map.values():
        tools = getattr(agent, "tools", None)
        if not isinstance(tools, list):
            continue
        for tool in tools:
            if not isinstance(tool, HostedMCPToolRuntime):
                continue
            tool_config = getattr(tool, "tool_config", None)
            if not isinstance(tool_config, dict):
                continue
            if not isinstance(tool_config.get("server_url"), str) or tool_config.get("server_url") == "":
                continue
            if tool_config.get("authorization") in (None, ""):
                return True
    return False


class FastAPIOAuthRuntime:
    """Per-request OAuth coordinator for FastAPI streaming."""

    def __init__(self, registry: OAuthStateRegistry, user_id: str | None, *, timeout: float | None = 300.0) -> None:
        self.registry = registry
        self.user_id = user_id
        self.timeout = timeout
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._state_by_server: dict[str, str] = {}

    async def handle_redirect(self, auth_url: str, server_name: str | None) -> None:
        """Record redirect metadata and notify listeners."""
        state = extract_state_from_url(auth_url)
        key = server_name or state
        self._state_by_server[key] = state
        await self.registry.record_redirect(
            state=state, auth_url=auth_url, server_name=server_name, user_id=self.user_id
        )
        await self._queue.put({"type": "oauth_redirect", "state": state, "auth_url": auth_url, "server": server_name})
        await self._queue.put({"type": "oauth_status", "state": state, "status": "pending", "server": server_name})

    async def wait_for_code(self, server_name: str | None) -> tuple[str, str | None]:
        """Block until the callback delivers code/state for the provided server."""
        key = server_name or next(iter(self._state_by_server), None)
        if key is None or key not in self._state_by_server:
            raise OAuthFlowError("OAuth state not initialized before callback wait")
        state = self._state_by_server[key]
        try:
            code, resolved_state = await self.registry.wait_for_code(state=state, timeout=self.timeout)
        except OAuthFlowError:
            snapshot = await self.registry.get_status(state)
            await self._queue.put(
                {
                    "type": "oauth_status",
                    "state": state,
                    "status": snapshot.get("status", "error:unknown"),
                    "server": server_name,
                }
            )
            raise
        await self._queue.put(
            {"type": "oauth_status", "state": resolved_state, "status": "authorized", "server": server_name}
        )
        return code, resolved_state

    async def next_event(self) -> dict[str, Any]:
        """Return the next OAuth event destined for the SSE stream."""
        return await self._queue.get()

    def redirect_handler_factory(self):
        """Build per-server redirect handlers for request-scoped OAuth runtime context."""

        def _factory(server_name: str | None):
            return lambda auth_url, server_name=server_name: self.handle_redirect(auth_url, server_name)

        return _factory

    def callback_handler_factory(self):
        """Build per-server callback handlers for request-scoped OAuth runtime context."""

        def _factory(server_name: str | None):
            return lambda server_name=server_name: self.wait_for_code(server_name)

        return _factory

    def install_handler_factory(self, agent: Any) -> None:
        """Attach per-server handler factory to agents with OAuth servers.

        This must be called for each request to ensure OAuth events go to the
        current request's queue, not a stale one from a previous request.
        """
        servers = getattr(agent, "mcp_servers", None)
        has_oauth_servers = isinstance(servers, list) and any(is_oauth_server(srv) for srv in servers)
        tools = getattr(agent, "tools", None)
        has_hosted_mcp_tools = (
            HostedMCPToolRuntime is not None
            and isinstance(tools, list)
            and any(isinstance(tool, HostedMCPToolRuntime) for tool in tools)
        )
        if not has_oauth_servers and not has_hosted_mcp_tools:
            return

        redirect_factory = self.redirect_handler_factory()
        callback_factory = self.callback_handler_factory()

        def _factory(server_name: str) -> dict[str, Any]:
            return {
                "redirect": redirect_factory(server_name),
                "callback": callback_factory(server_name),
            }

        agent.mcp_oauth_handler_factory = _factory


@dataclass
class FastAPIOAuthConfig:
    """Configuration passed into FastAPI endpoint factories."""

    registry: OAuthStateRegistry
    user_header: str = "X-User-Id"
    timeout: float | None = 600.0

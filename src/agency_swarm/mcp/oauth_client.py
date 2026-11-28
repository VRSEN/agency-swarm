"""OAuth-authenticated MCP client for Agency Swarm."""

import asyncio
from typing import Any, TypedDict

from agents import RunContextWrapper
from agents.agent import AgentBase
from agents.exceptions import UserError
from agents.mcp.server import MCPServerStreamableHttp
from mcp.types import (
    CallToolResult,
    GetPromptResult,
    ListPromptsResult,
    ListResourcesResult,
    ListResourceTemplatesResult,
    ReadResourceResult,
    Tool as MCPTool,
)
from pydantic import AnyUrl

from .oauth import (
    MCPServerOAuth,
    OAuthCallbackHandler,
    OAuthRedirectHandler,
    create_oauth_provider,
)
from .oauth_provider import ErrorCapturingOAuthClientProvider


class OAuthHandlerMap(TypedDict, total=False):
    redirect: OAuthRedirectHandler
    callback: OAuthCallbackHandler


class MCPServerOAuthClient(MCPServerStreamableHttp):
    """Agents SDK ``MCPServerStreamableHttp`` subclass that runs OAuth when it connects.

    Agency Swarm connects OAuth servers on demand, so each MCP call connects first when needed.
    Mirrors ``agents.mcp.server.MCPServerStreamableHttp`` with ``max_list_pages`` forwarded from
    ``oauth_config`` or constructor kwargs. Other ``MCPServerStreamableHttp.__init__`` knobs
    (``cache_tools_list``, ``tool_filter``, ``use_structured_content``, ``max_retry_attempts``,
    ``retry_backoff_seconds_base``, ``retry_backoff_seconds_max``, ``message_handler``,
    ``require_approval``, ``failure_error_function``, ``tool_meta_resolver``,
    ``custom_data_extractor``, ``tool_input_guardrails``, ``tool_output_guardrails``) stay on SDK
    defaults because OAuth server construction is driven by :class:`MCPServerOAuth`.
    """

    def __init__(
        self,
        oauth_config: MCPServerOAuth,
        custom_handlers: OAuthHandlerMap | None = None,
        *,
        max_list_pages: int | None = None,
    ) -> None:
        resolved_max_list_pages = max_list_pages if max_list_pages is not None else oauth_config.max_list_pages
        # OAuth consent runs while the MCP session initializes, so the session read timeout stays off.
        super().__init__(
            params={"url": oauth_config.url, "timeout": 30.0, "sse_read_timeout": 300.0},
            name=oauth_config.name,
            client_session_timeout_seconds=None,
            max_list_pages=resolved_max_list_pages,
        )
        self.oauth_config = oauth_config
        handlers = custom_handlers or {}
        self._redirect_handler: OAuthRedirectHandler | None = handlers.get("redirect")
        self._callback_handler: OAuthCallbackHandler | None = handlers.get("callback")
        self._oauth_provider: ErrorCapturingOAuthClientProvider | None = None

    async def connect(self) -> None:
        """Create a fresh OAuth provider and connect through the Agents SDK."""
        if self.session is not None:
            return
        provider = await create_oauth_provider(
            self.oauth_config,
            redirect_handler=self._redirect_handler,
            callback_handler=self._callback_handler,
        )
        self._oauth_provider = provider
        self.params["auth"] = provider
        try:
            await super().connect()
        except (asyncio.CancelledError, UserError) as exc:
            # The MCP HTTP writer logs and swallows OAuth errors, so they surface as a cancellation
            # or as the SDK's generic connection error. Raise the OAuth error the provider captured.
            flow_error = provider.pop_last_flow_error()
            if flow_error is None:
                raise
            raise flow_error from exc

    async def _connect_if_needed(self) -> None:
        if self.session is None:
            await self.connect()

    async def list_tools(
        self,
        run_context: RunContextWrapper[Any] | None = None,
        agent: AgentBase[Any] | None = None,
    ) -> list[MCPTool]:
        await self._connect_if_needed()
        return await super().list_tools(run_context, agent)

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> CallToolResult:
        await self._connect_if_needed()
        return await super().call_tool(tool_name, arguments, meta)

    async def list_prompts(self) -> ListPromptsResult:
        await self._connect_if_needed()
        return await super().list_prompts()

    async def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> GetPromptResult:
        await self._connect_if_needed()
        return await super().get_prompt(name, arguments)

    async def list_resources(self, cursor: str | None = None) -> ListResourcesResult:
        await self._connect_if_needed()
        return await super().list_resources(cursor)

    async def list_resource_templates(self, cursor: str | None = None) -> ListResourceTemplatesResult:
        await self._connect_if_needed()
        return await super().list_resource_templates(cursor)

    async def read_resource(self, uri: str | AnyUrl) -> ReadResourceResult:
        await self._connect_if_needed()
        return await super().read_resource(str(uri))

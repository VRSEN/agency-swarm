"""Request override session lifecycle and agency state snapshots."""

import contextlib
import copy
import logging
from dataclasses import dataclass
from typing import Any, cast

from agents import Model, ModelSettings
from openai import AsyncOpenAI, OpenAI

from agency_swarm import Agency
from agency_swarm.integrations.fastapi_utils import endpoint_handlers
from agency_swarm.integrations.fastapi_utils.override_policy import RequestOverridePolicy
from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
from agency_swarm.integrations.fastapi_utils.request_state import _AgencyRequestLease
from agency_swarm.utils import hosted_tool_compat

# Keep the pre-split logger name so log records are unchanged.
logger = logging.getLogger("agency_swarm.integrations.fastapi_utils.endpoint_handlers")


type _AgentStateSnapshot = tuple[
    str | Model | None,
    ModelSettings | None,
    AsyncOpenAI | None,
    OpenAI | None,
    hosted_tool_compat.ToolSnapshot,
    hosted_tool_compat.AttachmentCompatibilitySnapshot,
]
type _AgencyStateSnapshot = dict[str, _AgentStateSnapshot]
type _OAuthAgentStateSnapshot = dict[
    str,
    tuple[
        list[Any] | None,
        list[Any] | None,
        dict[str, Any],
        bool,
        bool,
        Any,
        Any,
        dict[str, list[Any]] | None,
        str | None,
    ],
]


_ATTR_MISSING = object()


@dataclass
class _RequestOverrideSession:
    """Track request override lifecycle for one handler invocation."""

    agency: Agency
    policy: RequestOverridePolicy
    restore_oauth_state: bool = False
    lease: _AgencyRequestLease | None = None
    restore_snapshot: _AgencyStateSnapshot | None = None
    oauth_snapshot: _OAuthAgentStateSnapshot | None = None
    _is_cleaned: bool = False

    async def acquire(self) -> None:
        self.lease = await endpoint_handlers._acquire_agency_request_lease(
            self.agency,
            is_override=self.policy.has_client_overrides or self.restore_oauth_state,
        )
        if self.restore_oauth_state:
            self.oauth_snapshot = _snapshot_oauth_agent_state(self.agency)
        if self.policy.has_client_overrides and self.policy.config is not None:
            self.restore_snapshot = _snapshot_agency_state(self.agency)
            endpoint_handlers.apply_openai_client_config(self.agency, self.policy.config)
            for agent in self.agency.agents.values():
                hosted_tool_compat.enable_attachment_compatibility(agent)

    async def cleanup(self) -> None:
        if self._is_cleaned:
            return
        self._is_cleaned = True
        primary_error: BaseException | None = None

        def preserve_primary_error(error: BaseException) -> None:
            nonlocal primary_error
            if primary_error is None:
                primary_error = error

        if self.restore_oauth_state:
            try:
                await endpoint_handlers.cleanup_oauth_runtime_mcp_servers()
            except BaseException as exc:
                preserve_primary_error(exc)
            try:
                endpoint_handlers.restore_hosted_mcp_oauth_tools(self.agency)
            except BaseException as exc:
                preserve_primary_error(exc)
        if self.oauth_snapshot is not None:
            try:
                endpoint_handlers._restore_oauth_agent_state(self.agency, self.oauth_snapshot)
            except BaseException as exc:
                preserve_primary_error(exc)
        if self.restore_snapshot is not None:
            try:
                endpoint_handlers._restore_agency_state(self.agency, self.restore_snapshot)
            except BaseException as exc:
                preserve_primary_error(exc)
        if self.lease is not None:
            try:
                await endpoint_handlers._release_agency_request_lease(self.lease)
            except BaseException as exc:
                self._is_cleaned = False
                preserve_primary_error(exc)
            else:
                self.lease = None
        if primary_error is not None:
            raise primary_error


def _has_request_client_overrides(config: ClientConfig | None) -> bool:
    """Return True when request client_config carries any override values."""
    return RequestOverridePolicy(config).has_client_overrides


def _has_request_openai_overrides(config: ClientConfig | None) -> bool:
    """Return True when request client_config carries OpenAI client overrides."""
    return RequestOverridePolicy(config).has_openai_overrides


def _build_file_upload_client(
    agency: Agency,
    config: ClientConfig | None,
    recipient_agent: str | None = None,
) -> AsyncOpenAI | None:
    """Build a request-scoped OpenAI client for file uploads when overrides are present."""
    return RequestOverridePolicy(config).build_file_upload_client(agency, recipient_agent=recipient_agent)


def _snapshot_agency_state(
    agency: Agency,
) -> _AgencyStateSnapshot:
    """Capture request-mutable agent state so overrides can be restored."""
    snapshot: _AgencyStateSnapshot = {}
    for name, agent in agency.agents.items():
        model_settings = getattr(agent, "model_settings", None)
        snapshot[name] = (
            agent.model,
            copy.deepcopy(model_settings) if model_settings is not None else None,
            getattr(agent, "_openai_client", None),
            getattr(agent, "_openai_client_sync", None),
            list(agent.tools) if hasattr(agent, "tools") else None,
            hosted_tool_compat.snapshot_attachment_compatibility(agent),
        )
    return snapshot


def _snapshot_oauth_agent_state(agency: Agency) -> _OAuthAgentStateSnapshot:
    """Capture agent tool/deferred-OAuth state mutated during one OAuth request."""
    snapshot: _OAuthAgentStateSnapshot = {}
    runtime_states = getattr(agency, "_agent_runtime_state", {})
    for name, agent in agency.agents.items():
        tools = getattr(agent, "tools", None)
        mcp_servers = getattr(agent, "mcp_servers", None)
        deferred_servers = getattr(agent, "_deferred_mcp_servers", {})
        runtime_state = runtime_states.get(name)
        snapshot[name] = (
            list(tools) if isinstance(tools, list) else None,
            list(mcp_servers) if isinstance(mcp_servers, list) else None,
            dict(deferred_servers) if isinstance(deferred_servers, dict) else {},
            bool(getattr(agent, "_mcp_tools_deferred", False)),
            bool(getattr(agent, "_mcp_tools_initialized", False)),
            getattr(agent, "mcp_oauth_handler_factory", _ATTR_MISSING),
            getattr(agent, "_hosted_mcp_oauth_enabled", _ATTR_MISSING),
            (
                {server_name: list(server_tools) for server_name, server_tools in runtime_state.oauth_mcp_tools.items()}
                if runtime_state is not None
                else None
            ),
            runtime_state.oauth_mcp_tools_user_id if runtime_state is not None else None,
        )
    return snapshot


def _restore_oauth_agent_state(agency: Agency, snapshot: _OAuthAgentStateSnapshot) -> None:
    """Restore agent tool/deferred-OAuth state after a FastAPI OAuth request."""
    runtime_states = getattr(agency, "_agent_runtime_state", {})
    for (
        name,
        (
            tools,
            mcp_servers,
            deferred_servers,
            mcp_tools_deferred,
            mcp_tools_initialized,
            handler_factory,
            hosted_mcp_oauth_enabled,
            oauth_mcp_tools,
            oauth_mcp_tools_user_id,
        ),
    ) in snapshot.items():
        agent = agency.agents.get(name)
        if agent is None:
            continue
        dynamic_agent = cast(Any, agent)
        if tools is not None:
            agent.tools = tools
        if mcp_servers is not None:
            agent.mcp_servers = mcp_servers
        dynamic_agent._deferred_mcp_servers = deferred_servers
        dynamic_agent._mcp_tools_deferred = mcp_tools_deferred
        dynamic_agent._mcp_tools_initialized = mcp_tools_initialized
        if handler_factory is _ATTR_MISSING:
            with contextlib.suppress(AttributeError):
                del dynamic_agent.mcp_oauth_handler_factory
        else:
            dynamic_agent.mcp_oauth_handler_factory = handler_factory
        if hosted_mcp_oauth_enabled is _ATTR_MISSING:
            with contextlib.suppress(AttributeError):
                del dynamic_agent._hosted_mcp_oauth_enabled
        else:
            dynamic_agent._hosted_mcp_oauth_enabled = hosted_mcp_oauth_enabled
        runtime_state = runtime_states.get(name)
        if runtime_state is not None and oauth_mcp_tools is not None:
            # Restore the owning user with the tools so a later request for a different
            # user can still detect the mismatch and drop them.
            runtime_state.oauth_mcp_tools = oauth_mcp_tools
            runtime_state.oauth_mcp_tools_user_id = oauth_mcp_tools_user_id


def _restore_agency_state(
    agency: Agency,
    snapshot: _AgencyStateSnapshot,
) -> None:
    for name, state in snapshot.items():
        model, model_settings, openai_client, openai_client_sync, tools, attachment_compatibility = state
        agent = agency.agents.get(name)
        if agent is None:
            continue
        agent.model = model
        agent.model_settings = cast(ModelSettings, model_settings)
        agent._openai_client = openai_client
        agent._openai_client_sync = openai_client_sync
        hosted_tool_compat.restore_tool_snapshot(agent, tools)
        hosted_tool_compat.restore_attachment_compatibility(agent, attachment_compatibility)

"""Apply endpoint-aware defaults to the SDK's ``RunConfig.tracing_disabled``.

The SDK configures model clients and its default ``BackendSpanExporter``
independently. This module only selects a per-run default; it does not replace
``TraceProvider`` or change process-wide tracing settings. Explicit SDK tracing
configuration, processors and active trace contexts retain their SDK behavior.
An enabled dynamic ``Handoff`` without a target reference defaults tracing off
because its endpoint cannot be verified before the run starts.

Only SDK OpenAI models/providers expose a typed OpenAI client endpoint. Other
``Model`` and ``ModelProvider`` implementations keep their existing tracing
behavior because the SDK defines no endpoint interface for them.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace

from agents import Agent as SDKAgent, Model, ModelProvider, RunConfig, RunContextWrapper
from agents.models._openai_shared import get_default_openai_client
from agents.models.multi_provider import MultiProvider
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.models.openai_client_utils import is_official_openai_base_url
from agents.models.openai_provider import OpenAIProvider
from agents.models.openai_responses import OpenAIResponsesModel, OpenAIResponsesWSModel
from agents.run_context import TContext
from agents.run_state import RunState
from agents.tracing import get_current_trace, get_trace_provider
from agents.tracing.processors import default_processor
from agents.tracing.provider import DefaultTraceProvider
from httpx2 import URL
from openai import AsyncOpenAI

from agency_swarm.context import MasterContext

_OPENAI_BASE_URL = "https://api.openai.com/v1"


def with_endpoint_tracing_defaults(
    agent: SDKAgent[TContext],
    run_config: RunConfig,
    *,
    run_state: RunState[TContext] | None = None,
    context: object | None = None,
) -> RunConfig:
    """Disable default tracing for custom OpenAI endpoints without mutating callers."""
    if run_config.tracing_disabled or _has_explicit_tracing(run_config):
        return run_config
    current = run_state._current_agent if run_state is not None and run_state._current_agent is not None else agent
    if _has_custom_endpoint(current, run_config):
        return replace(run_config, tracing_disabled=True)
    # Agency runs can delegate via SendMessage as well as SDK handoffs. Protect
    # their shared trace before a native entry agent creates it.
    if context is None and run_state is not None:
        context = run_state._context
    if isinstance(context, RunContextWrapper):
        context = context.context
    if isinstance(context, MasterContext):
        child_config = RunConfig()
        can_reenter = len(context.agents) > 1
        if any(
            (member is not current or can_reenter) and _has_custom_endpoint(member, child_config)
            for member in context.agents.values()
        ):
            return replace(run_config, tracing_disabled=True)
    return run_config


def _has_custom_endpoint(agent: SDKAgent[TContext], run_config: RunConfig) -> bool:
    for candidate in _handoff_agents(agent):
        if candidate is None:
            return True
        endpoint = _model_endpoint(candidate, run_config)
        if endpoint is not None and not _is_openai_endpoint(endpoint):
            return True
    return False


def _handoff_agents(agent: SDKAgent[TContext]) -> Iterator[SDKAgent[TContext] | None]:
    pending = [agent]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        yield current
        for target in current.handoffs:
            if isinstance(target, SDKAgent):
                pending.append(target)
            elif target.is_enabled is not False:
                resolved = target._agent_ref() if target._agent_ref is not None else None
                if isinstance(resolved, SDKAgent):
                    pending.append(resolved)
                else:
                    # A dynamic handoff has no statically verifiable endpoint.
                    yield None


def _has_explicit_tracing(run_config: RunConfig) -> bool:
    if run_config.tracing is not None or get_current_trace() is not None:
        return True
    flag = os.environ.get("OPENAI_AGENTS_DISABLE_TRACING", "").lower()
    if flag in {"0", "false", "1", "true"}:
        return True
    provider = get_trace_provider()
    if not isinstance(provider, DefaultTraceProvider):
        return True
    # SDK 0.22.3 has no public accessor for manual settings or installed processors.
    # Inspect its typed state so set_tracing_disabled(False) and collector setup
    # remain explicit choices rather than silently disabling those integrations.
    if provider._manual_disabled is not None:
        return True
    return provider._multi_processor._processors != (default_processor(),)


def _model_endpoint(agent: SDKAgent[TContext], run_config: RunConfig) -> URL | None:
    model = run_config.model if run_config.model is not None else agent.model
    if isinstance(model, OpenAIResponsesModel | OpenAIChatCompletionsModel):
        return _client_endpoint(model._client, websocket=isinstance(model, OpenAIResponsesWSModel))
    if isinstance(model, Model):
        return None
    return _provider_endpoint(run_config.model_provider, model)


def _provider_endpoint(provider: ModelProvider, model_name: str | None) -> URL | None:
    # Reuse the pinned SDK's routing/client resolution instead of duplicating its
    # prefix modes, provider-map precedence or default-client selection rules.
    if isinstance(provider, OpenAIProvider):
        return _openai_provider_endpoint(provider)
    if isinstance(provider, MultiProvider):
        prefix, stripped_name = provider._get_prefix_and_model_name(model_name)
        if prefix is None:
            return _provider_endpoint(provider.openai_provider, stripped_name)
        mapped = provider.provider_map.get_provider(prefix) if provider.provider_map is not None else None
        # Do not import optional providers or validate unknown model names before
        # SDK input guardrails have had a chance to reject the request.
        if mapped is None:
            if prefix in {"litellm", "any-llm"}:
                return None
            if prefix != "openai" and provider._unknown_prefix_mode != "model_id":
                return None
        assert model_name is not None
        routed, resolved_name = provider._resolve_prefixed_model(
            original_model_name=model_name,
            prefix=prefix,
            stripped_model_name=stripped_name,
        )
        return _provider_endpoint(routed, resolved_name)
    return None


def _openai_provider_endpoint(provider: OpenAIProvider) -> URL:
    # The SDK has no endpoint-only accessor. Inspect its pinned, typed config
    # rather than call _get_client(), which requires credentials and caches a
    # client before guardrails/hooks run. Preserve its explicit-option priority.
    client = provider._client
    if client is None and not any(
        value is not None
        for value in (
            provider._stored_api_key,
            provider._stored_base_url,
            provider._stored_websocket_base_url,
            provider._stored_organization,
            provider._stored_project,
        )
    ):
        client = get_default_openai_client()
    websocket = provider._use_responses and provider._responses_transport == "websocket"
    if client is not None:
        return _client_endpoint(client, websocket=websocket)
    base_url = provider._stored_base_url
    if base_url is None:
        base_url = os.environ.get("OPENAI_BASE_URL", _OPENAI_BASE_URL)
    ws_base = provider._stored_websocket_base_url
    if ws_base is None:
        ws_base = os.environ.get("OPENAI_WEBSOCKET_BASE_URL")
    return URL(ws_base if websocket and ws_base is not None else base_url)


def _client_endpoint(client: AsyncOpenAI | None, *, websocket: bool) -> URL:
    if client is None:
        return URL(os.environ.get("OPENAI_BASE_URL", _OPENAI_BASE_URL))
    if websocket and client.websocket_base_url is not None:
        return URL(client.websocket_base_url)
    return client.base_url


def _is_openai_endpoint(endpoint: URL) -> bool:
    # The SDK predicate recognizes its HTTPS/WSS host. An unusual port is a
    # different origin, so it also requires an explicit tracing choice.
    return is_official_openai_base_url(endpoint, websocket=endpoint.scheme == "wss") and endpoint.port in {None, 443}

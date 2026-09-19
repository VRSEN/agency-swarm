"""FastAPI endpoint handler factories and request helpers.

Public facade for the endpoint-handler implementation. The implementation is
split into focused submodules under ``agency_swarm.integrations.fastapi_utils``
(request state, override sessions, OAuth helpers, message builders, model and
client overrides, Codex compatibility, and the endpoint factories themselves);
this module re-exports the full surface so existing imports keep working.

Late-binding cycle (intentional): submodules import this facade module object
and resolve facade-level names through it at call time (for example
``endpoint_handlers.generate_chat_name(...)`` rather than an import-time bound
reference). Tests patch names on this facade, and call-time lookup keeps those
patches effective for internal call sites. Import through this module rather
than through the submodules directly.
"""

# ruff: noqa: F401 - this facade intentionally re-exports its implementation's surface

import asyncio
import contextlib
import copy
import json
import logging
import os
import threading
import time
import traceback
import uuid
from collections.abc import AsyncGenerator, Callable, Sequence
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any, Literal, cast
from weakref import ReferenceType, ref

from ag_ui.core import (
    AudioInputContent,
    BaseEvent,
    BinaryInputContent,
    DocumentInputContent,
    EventType,
    ImageInputContent,
    InputContentDataSource,
    InputContentUrlSource,
    Message,
    MessagesSnapshotEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    SystemMessage,
    TextInputContent,
    VideoInputContent,
)
from ag_ui.encoder import EventEncoder
from agents import (
    Model,
    ModelSettings,
    OpenAIChatCompletionsModel,
    OpenAIResponsesModel,
    TResponseInputItem,
    output_guardrail,
)
from agents.exceptions import OutputGuardrailTripwireTriggered
from agents.models._openai_shared import get_default_openai_client

# LiteLLM is optional - only available if the `litellm` extra is installed
try:
    from agents.extensions.models.litellm_model import LitellmModel

    _LITELLM_AVAILABLE = True
except ImportError:
    _LITELLM_AVAILABLE = False
    LitellmModel = None  # type: ignore[misc, assignment]
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import AsyncOpenAI, OpenAI
from openai.types.shared.reasoning import Reasoning
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from agency_swarm import (
    Agency,
    Agent,
    GuardrailFunctionOutput,
    RunContextWrapper,
)
from agency_swarm.agent.execution_stream_response import StreamingRunResponse
from agency_swarm.agent.initialization import apply_framework_defaults
from agency_swarm.integrations.fastapi_utils.agui_endpoint import (
    make_agui_chat_endpoint as make_agui_chat_endpoint,
)
from agency_swarm.integrations.fastapi_utils.client_overrides import (
    _AGENCY_SWARM_DEFAULT_MODEL as _AGENCY_SWARM_DEFAULT_MODEL,
    _apply_default_headers_to_agent_model_settings as _apply_default_headers_to_agent_model_settings,
    _apply_openai_clients_to_agent as _apply_openai_clients_to_agent,
    _apply_openrouter_file_clients_to_agent as _apply_openrouter_file_clients_to_agent,
    _apply_request_scoped_openai_clients_to_agent as _apply_request_scoped_openai_clients_to_agent,
    _build_openai_client_for_agent as _build_openai_client_for_agent,
    _build_request_scoped_openai_client as _build_request_scoped_openai_client,
    _is_request_base_url as _is_request_base_url,
    _resolve_stream_client_config as _resolve_stream_client_config,
    _uses_openrouter_request_client as _uses_openrouter_request_client,
    apply_openai_client_config as apply_openai_client_config,
)
from agency_swarm.integrations.fastapi_utils.codex_compat import (
    _apply_codex_compatibility_model_settings as _apply_codex_compatibility_model_settings,
    _codex_output_item_key as _codex_output_item_key,
    _codex_output_sort_key as _codex_output_sort_key,
    _CodexAsyncStream as _CodexAsyncStream,
    _CodexStreamedOutputItem as _CodexStreamedOutputItem,
    _merge_codex_completed_output as _merge_codex_completed_output,
)
from agency_swarm.integrations.fastapi_utils.file_handler import upload_from_urls
from agency_swarm.integrations.fastapi_utils.litellm_client_config import (
    _agent_supports_openai_client_override as _agent_supports_openai_client_override,
    _agent_uses_litellm as _agent_uses_litellm,
    _apply_client_to_agent as _apply_client_to_agent,
    _apply_litellm_config as _apply_litellm_config,
    _build_openai_model_for_client as _build_openai_model_for_client,
    _get_litellm_provider as _get_litellm_provider,
    _get_model_name_for_override_logging as _get_model_name_for_override_logging,
    _is_litellm_model as _is_litellm_model,
    _is_local_litellm_provider as _is_local_litellm_provider,
    _is_openai_based_litellm_provider as _is_openai_based_litellm_provider,
    _is_openai_model_name as _is_openai_model_name,
    _log_unsupported_client_override as _log_unsupported_client_override,
    _normalize_litellm_model_name as _normalize_litellm_model_name,
    _resolve_litellm_api_key as _resolve_litellm_api_key,
    _resolve_litellm_base_url as _resolve_litellm_base_url,
    _should_reuse_source_openai_client as _should_reuse_source_openai_client,
    _should_wrap_openrouter_override_with_openai_client as _should_wrap_openrouter_override_with_openai_client,
)
from agency_swarm.integrations.fastapi_utils.logging_middleware import get_logs_endpoint_impl
from agency_swarm.integrations.fastapi_utils.message_builders import (
    _build_agui_message_input as _build_agui_message_input,
    _build_agui_snapshot_messages as _build_agui_snapshot_messages,
    _build_chat_name_messages as _build_chat_name_messages,
    _build_data_url as _build_data_url,
    _build_message_with_file_urls_context as _build_message_with_file_urls_context,
    _convert_agui_binary_content_part as _convert_agui_binary_content_part,
    _convert_agui_content_part as _convert_agui_content_part,
    _convert_agui_file_content_part as _convert_agui_file_content_part,
    _convert_agui_image_content_part as _convert_agui_image_content_part,
    _format_file_urls_context as _format_file_urls_context,
    _is_file_urls_context_message as _is_file_urls_context_message,
    _normalize_agui_history_messages as _normalize_agui_history_messages,
    _normalize_new_messages_for_client as _normalize_new_messages_for_client,
)
from agency_swarm.integrations.fastapi_utils.model_override import (
    _MODEL_FAMILY_DEFAULT_FIELDS as _MODEL_FAMILY_DEFAULT_FIELDS,
    _OPENAI_CREDENTIAL_HEADER_NAMES as _OPENAI_CREDENTIAL_HEADER_NAMES,
    _apply_request_litellm_model as _apply_request_litellm_model,
    _apply_request_model_override as _apply_request_model_override,
    _client_base_url as _client_base_url,
    _copy_source_openai_client_for_openrouter as _copy_source_openai_client_for_openrouter,
    _copyable_source_openai_headers as _copyable_source_openai_headers,
    _openrouter_override_default_headers as _openrouter_override_default_headers,
    _rebuild_openai_responses_model as _rebuild_openai_responses_model,
    _refresh_framework_defaults_after_model_swap as _refresh_framework_defaults_after_model_swap,
    _resolve_openai_client_after_openrouter_override as _resolve_openai_client_after_openrouter_override,
    _resolve_request_gateway_client as _resolve_request_gateway_client,
    _should_copy_source_openai_client_for_openrouter as _should_copy_source_openai_client_for_openrouter,
    _should_preserve_source_openai_headers as _should_preserve_source_openai_headers,
)
from agency_swarm.integrations.fastapi_utils.model_settings_extra_args import (
    ReasoningEffortValue as ReasoningEffortValue,
    ReasoningSummaryValue as ReasoningSummaryValue,
    _apply_request_model_settings_extra_args as _apply_request_model_settings_extra_args,
    _has_enabled_thinking_budget as _has_enabled_thinking_budget,
    _is_gateway_provider_variant as _is_gateway_provider_variant,
    _litellm_model_name as _litellm_model_name,
    _move_gateway_variant_extra_args as _move_gateway_variant_extra_args,
    _normalize_anthropic_litellm_variant_args as _normalize_anthropic_litellm_variant_args,
    _normalize_gemini_litellm_variant_args as _normalize_gemini_litellm_variant_args,
    _normalize_thinking_budget_tokens as _normalize_thinking_budget_tokens,
    _normalize_xai_litellm_variant_args as _normalize_xai_litellm_variant_args,
    _reasoning_effort_value as _reasoning_effort_value,
    _reasoning_summary_value as _reasoning_summary_value,
    _request_model_name as _request_model_name,
    _xai_litellm_model_supports_reasoning_effort as _xai_litellm_model_supports_reasoning_effort,
)
from agency_swarm.integrations.fastapi_utils.oauth_helpers import (
    OAUTH_KEEPALIVE_SECONDS as OAUTH_KEEPALIVE_SECONDS,
    _clear_oauth_request_context as _clear_oauth_request_context,
    _ensure_request_oauth_config as _ensure_request_oauth_config,
    _has_enabled_hosted_mcp_oauth as _has_enabled_hosted_mcp_oauth,
    _has_oauth_servers as _has_oauth_servers,
    _no_oauth_user_id as _no_oauth_user_id,
    _prepare_oauth_runtime as _prepare_oauth_runtime,
    _requires_oauth_agent_state_restore as _requires_oauth_agent_state_restore,
    _resolve_oauth_user_id as _resolve_oauth_user_id,
    _set_oauth_runtime_context as _set_oauth_runtime_context,
    _set_oauth_user_context as _set_oauth_user_context,
    _sse_keepalive_comment as _sse_keepalive_comment,
    _update_oauth_pending as _update_oauth_pending,
    _with_oauth_user_context as _with_oauth_user_context,
)
from agency_swarm.integrations.fastapi_utils.oauth_support import (
    FastAPIOAuthConfig,
    FastAPIOAuthRuntime,
    has_hosted_mcp_oauth_tools,
    has_hosted_mcp_tools_missing_authorization,
    is_oauth_server,
)
from agency_swarm.integrations.fastapi_utils.override_policy import (
    RequestOverridePolicy,
    _get_cached_openai_client_from_agent,
    _get_openai_client_from_agent,
    get_allowed_dirs_for_metadata,
)
from agency_swarm.integrations.fastapi_utils.override_session import (
    _ATTR_MISSING as _ATTR_MISSING,
    _AgencyStateSnapshot as _AgencyStateSnapshot,
    _AgentStateSnapshot as _AgentStateSnapshot,
    _build_file_upload_client as _build_file_upload_client,
    _has_request_client_overrides as _has_request_client_overrides,
    _has_request_openai_overrides as _has_request_openai_overrides,
    _OAuthAgentStateSnapshot as _OAuthAgentStateSnapshot,
    _RequestOverrideSession as _RequestOverrideSession,
    _restore_agency_state as _restore_agency_state,
    _restore_oauth_agent_state as _restore_oauth_agent_state,
    _snapshot_agency_state as _snapshot_agency_state,
    _snapshot_oauth_agent_state as _snapshot_oauth_agent_state,
)
from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
from agency_swarm.integrations.fastapi_utils.request_state import (
    _AGENCY_REQUEST_STATES_GUARD as _AGENCY_REQUEST_STATES_GUARD,
    _AGENT_REQUEST_STATES as _AGENT_REQUEST_STATES,
    _acquire_agency_request_lease as _acquire_agency_request_lease,
    _acquire_request_state as _acquire_request_state,
    _AgencyRequestLease as _AgencyRequestLease,
    _AgencyRequestState as _AgencyRequestState,
    _get_agency_request_states as _get_agency_request_states,
    _get_identity_request_state as _get_identity_request_state,
    _release_agency_request_lease as _release_agency_request_lease,
    _release_request_state as _release_request_state,
    _remove_request_state_entry as _remove_request_state_entry,
    _RequestStateEntry as _RequestStateEntry,
)
from agency_swarm.integrations.fastapi_utils.response_endpoints import (
    _get_agency_swarm_version as _get_agency_swarm_version,
    exception_handler as exception_handler,
    generate_chat_name as generate_chat_name,
    make_logs_endpoint as make_logs_endpoint,
    make_metadata_endpoint as make_metadata_endpoint,
    make_response_endpoint as make_response_endpoint,
)
from agency_swarm.integrations.fastapi_utils.run_registry import (
    ActiveRun as ActiveRun,
    ActiveRunRegistry as ActiveRunRegistry,
    get_verify_token as get_verify_token,
    make_cancel_endpoint as make_cancel_endpoint,
)
from agency_swarm.integrations.fastapi_utils.stream_endpoint import (
    make_stream_endpoint as make_stream_endpoint,
)
from agency_swarm.messages import MessageFilter, MessageFormatter
from agency_swarm.messages.codex_input import (
    is_codex_base_url as _is_codex_base_url,
    rewrite_system_input_roles_for_codex,
)
from agency_swarm.messages.response_input_sanitizer import (
    REASONING_ENCRYPTED_CONTENT_INCLUDE,
    ensure_store_false_reasoning_encrypted_content,
    sanitize_store_false_responses_input,
)
from agency_swarm.streaming.id_normalizer import StreamIdNormalizer
from agency_swarm.tools.mcp_manager import (
    attach_persistent_mcp_servers,
    cleanup_oauth_runtime_mcp_servers,
    restore_hosted_mcp_oauth_tools,
)
from agency_swarm.ui.core.agui_adapter import AguiAdapter
from agency_swarm.utils import hosted_tool_compat
from agency_swarm.utils.dry_run import force_dry_run
from agency_swarm.utils.openrouter import (
    OPENROUTER_API_KEY_ENV,
    OPENROUTER_BASE_URL,
    build_openrouter_chat_model,
    get_openrouter_model_name,
    is_openrouter_model_name,
)
from agency_swarm.utils.serialization import serialize
from agency_swarm.utils.usage_tracking import (
    calculate_usage_with_cost,
    extract_usage_from_run_result,
)

# The shared request-state registry is stored on this facade so a replaced
# ``endpoint_handlers._AGENT_REQUEST_STATES`` (as tests do via monkeypatch) is
# honored by every submodule, which reads it through this module at call time.
_AGENT_REQUEST_STATES: dict[int, _RequestStateEntry] = _AGENT_REQUEST_STATES
_MODEL_FAMILY_DEFAULT_FIELDS: tuple[str, ...] = _MODEL_FAMILY_DEFAULT_FIELDS

logger = logging.getLogger(__name__)

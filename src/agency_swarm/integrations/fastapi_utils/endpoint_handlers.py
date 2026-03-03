import asyncio
import copy
import json
import logging
import threading
import time
import traceback
import uuid
from collections.abc import AsyncGenerator, Callable, Sequence
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import cast
from weakref import WeakKeyDictionary

from ag_ui.core import EventType, MessagesSnapshotEvent, RunErrorEvent, RunFinishedEvent, RunStartedEvent
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

# LiteLLM is optional - only available if openai-agents[litellm] is installed
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
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from agency_swarm import (
    Agency,
    Agent,
    GuardrailFunctionOutput,
    RunContextWrapper,
)
from agency_swarm.agent.execution_stream_response import StreamingRunResponse
from agency_swarm.integrations.fastapi_utils.file_handler import upload_from_urls
from agency_swarm.integrations.fastapi_utils.logging_middleware import get_logs_endpoint_impl
from agency_swarm.integrations.fastapi_utils.override_policy import (
    RequestOverridePolicy,
    _get_openai_client_from_agent,
    get_allowed_dirs_for_metadata,
)
from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
from agency_swarm.messages import MessageFilter, MessageFormatter
from agency_swarm.streaming.id_normalizer import StreamIdNormalizer
from agency_swarm.tools.mcp_manager import attach_persistent_mcp_servers
from agency_swarm.ui.core.agui_adapter import AguiAdapter
from agency_swarm.utils.serialization import serialize
from agency_swarm.utils.usage_tracking import (
    calculate_usage_with_cost,
    extract_usage_from_run_result,
)

logger = logging.getLogger(__name__)

type _AgencyStateSnapshot = dict[
    str,
    tuple[str | Model | None, ModelSettings | None, AsyncOpenAI | None, OpenAI | None],
]


@dataclass
class _AgencyRequestState:
    """Per-agency request coordination state for one event loop."""

    state_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    active_regular_requests: int = 0
    override_active: bool = False
    pending_overrides: int = 0
    state_changed: asyncio.Condition = field(init=False)

    def __post_init__(self) -> None:
        self.state_changed = asyncio.Condition(self.state_lock)


@dataclass
class _AgencyRequestLease:
    state: _AgencyRequestState
    is_override: bool


@dataclass
class _RequestOverrideSession:
    """Track request override lifecycle for one handler invocation."""

    agency: Agency
    policy: RequestOverridePolicy
    lease: _AgencyRequestLease | None = None
    restore_snapshot: _AgencyStateSnapshot | None = None
    _is_cleaned: bool = False

    async def acquire(self) -> None:
        self.lease = await _acquire_agency_request_lease(self.agency, is_override=self.policy.has_client_overrides)
        if self.policy.has_client_overrides and self.policy.config is not None:
            self.restore_snapshot = _snapshot_agency_state(self.agency)
            apply_openai_client_config(self.agency, self.policy.config)

    async def cleanup(self) -> None:
        if self._is_cleaned:
            return
        self._is_cleaned = True
        if self.restore_snapshot is not None:
            _restore_agency_state(self.agency, self.restore_snapshot)
        if self.lease is not None:
            await _release_agency_request_lease(self.lease)


_AGENCY_REQUEST_STATES: WeakKeyDictionary[Agency, dict[asyncio.AbstractEventLoop, _AgencyRequestState]] = (
    WeakKeyDictionary()
)
_AGENCY_REQUEST_STATES_GUARD = threading.Lock()


def apply_openai_client_config(agency: Agency, config: ClientConfig) -> None:
    """Apply custom OpenAI client configuration to all agents in the agency.

    Creates a new AsyncOpenAI client with the provided base_url and/or api_key,
    then updates each agent's model to use this client. This allows per-request
    client configuration without rebuilding templates.

    Parameters
    ----------
    agency : Agency
        The agency instance to configure.
    config : ClientConfig
        Configuration containing base_url and/or api_key overrides.
    """
    if (
        config.base_url is None
        and config.api_key is None
        and config.default_headers is None
        and config.litellm_keys is None
    ):
        return  # Nothing to override

    openai_overrides_present = (
        config.base_url is not None or config.api_key is not None or config.default_headers is not None
    )
    litellm_overrides_present = (
        config.base_url is not None or config.api_key is not None or config.litellm_keys is not None
    )

    # Apply to all agents in the agency
    for agent in agency.agents.values():
        # File attachment handling uses agent.client / agent.client_sync directly.
        # Keep those clients request-scoped too, so file_ids work without server env keys.
        if openai_overrides_present:
            _apply_request_scoped_openai_clients_to_agent(agent, config)

        if _agent_uses_litellm(agent):
            if config.default_headers is not None:
                _apply_default_headers_to_agent_model_settings(agent, config.default_headers)
            if not litellm_overrides_present:
                continue
            _apply_client_to_agent(agent, None, config)
            continue

        if not openai_overrides_present:
            continue

        if not _agent_supports_openai_client_override(agent):
            _log_unsupported_client_override(agent)
            continue

        client = _build_openai_client_for_agent(agent, config)
        _apply_client_to_agent(agent, client, config)


@dataclass
class ActiveRun:
    """Tracks an active streaming run for cancellation support."""

    stream: StreamingRunResponse
    agency: Agency
    initial_message_count: int
    cancelled: bool = field(default=False)
    cancel_mode: str | None = field(default=None)
    done_event: asyncio.Event = field(default_factory=asyncio.Event)


class ActiveRunRegistry:
    """Async-safe registry for active runs so cancel endpoints see local state."""

    def __init__(self) -> None:
        self._runs: dict[str, ActiveRun] = {}
        self._lock = asyncio.Lock()

    async def register(self, run_id: str, run: ActiveRun) -> None:
        async with self._lock:
            self._runs[run_id] = run

    async def get(self, run_id: str) -> ActiveRun | None:
        async with self._lock:
            return self._runs.get(run_id)

    async def mark_cancelled(self, run_id: str, cancel_mode: str) -> ActiveRun | None:
        async with self._lock:
            run = self._runs.get(run_id)
            if run is not None:
                run.cancelled = True
                run.cancel_mode = cancel_mode
            return run

    async def finish(self, run_id: str) -> ActiveRun | None:
        async with self._lock:
            run = self._runs.pop(run_id, None)
        if run is not None:
            run.done_event.set()
        return run


def get_verify_token(app_token):
    auto_error = app_token is not None and app_token != ""
    security = HTTPBearer(auto_error=auto_error)

    async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):  # noqa: B008
        if app_token is None or app_token == "":
            return None
        if not credentials or credentials.credentials != app_token:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return credentials.credentials

    return verify_token


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


# Non‑streaming response endpoint
def make_response_endpoint(
    request_model,
    agency_factory: Callable[..., Agency],
    verify_token,
    allowed_local_dirs: Sequence[str | Path] | None = None,
):
    async def handler(request: request_model, token: str = Depends(verify_token)):
        if request.chat_history is not None:
            # Chat history is now a flat list
            def load_callback() -> list:
                return request.chat_history
        else:

            def load_callback() -> list:
                return []

        agency_instance = agency_factory(load_threads_callback=load_callback)
        override_policy = RequestOverridePolicy(request.client_config)
        override_session = _RequestOverrideSession(agency=agency_instance, policy=override_policy)
        request_upload_client: AsyncOpenAI | None = None

        combined_file_ids = request.file_ids
        file_ids_map = None

        try:
            await override_session.acquire()

            request_upload_client = _build_file_upload_client(
                agency_instance,
                request.client_config,
                recipient_agent=request.recipient_agent,
            )

            if request.file_urls is not None:
                try:
                    file_ids_map = await upload_from_urls(
                        request.file_urls,
                        allowed_local_dirs=allowed_local_dirs,
                        openai_client=request_upload_client,
                    )
                    combined_file_ids = (combined_file_ids or []) + list(file_ids_map.values())
                except Exception as e:
                    return {"error": f"Error downloading file from provided urls: {e}"}

            # Attach persistent MCP servers and ensure connections before handling the request
            await attach_persistent_mcp_servers(agency_instance)

            # Capture initial message count to identify new messages
            initial_message_count = len(agency_instance.thread_manager.get_all_messages())

            response = await agency_instance.get_response(
                message=request.message,
                recipient_agent=request.recipient_agent,
                context_override=request.user_context,
                additional_instructions=request.additional_instructions,
                file_ids=combined_file_ids,
            )
            # Get only new messages added during this request
            all_messages = agency_instance.thread_manager.get_all_messages()
            new_messages = all_messages[initial_message_count:]  # Only messages added during this request
            filtered_messages = MessageFilter.filter_messages(new_messages)
            filtered_messages = _normalize_new_messages_for_client(filtered_messages)
            result = {"response": response.final_output, "new_messages": filtered_messages}

            # Extract and add usage information
            usage_stats = extract_usage_from_run_result(response)
            if usage_stats:
                # Calculate cost - model_name is auto-extracted from run_result._main_agent_model
                usage_stats = calculate_usage_with_cost(usage_stats, run_result=response)
                result["usage"] = usage_stats.to_dict()

            if request.file_urls is not None and file_ids_map is not None:
                result["file_ids_map"] = file_ids_map
            if request.generate_chat_name:
                try:
                    result["chat_name"] = await generate_chat_name(
                        filtered_messages,
                        openai_client=request_upload_client,
                    )
                except Exception as e:
                    # Do not add errors to the result as they might be mistaken for chat name
                    logger.error(f"Error generating chat name: {e}")
            return result
        finally:
            await override_session.cleanup()

    return handler


# Streaming SSE endpoint
def make_stream_endpoint(
    request_model,
    agency_factory: Callable[..., Agency],
    verify_token,
    run_registry: ActiveRunRegistry,
    allowed_local_dirs: Sequence[str | Path] | None = None,
):
    async def handler(
        http_request: Request,
        request: request_model,
        token: str = Depends(verify_token),
    ):
        if request.chat_history is not None:
            # Chat history is now a flat list
            def load_callback() -> list:
                return request.chat_history
        else:

            def load_callback() -> list:
                return []

        agency_instance = agency_factory(load_threads_callback=load_callback)
        override_policy = RequestOverridePolicy(request.client_config)
        override_session = _RequestOverrideSession(agency=agency_instance, policy=override_policy)
        request_upload_client: AsyncOpenAI | None = None

        combined_file_ids = request.file_ids
        file_ids_map = None

        async def cleanup_setup_context() -> None:
            await override_session.cleanup()

        try:
            await override_session.acquire()

            request_upload_client = _build_file_upload_client(
                agency_instance,
                request.client_config,
                recipient_agent=request.recipient_agent,
            )
            if request.file_urls is not None:
                try:
                    file_ids_map = await upload_from_urls(
                        request.file_urls,
                        allowed_local_dirs=allowed_local_dirs,
                        openai_client=request_upload_client,
                    )
                    combined_file_ids = (combined_file_ids or []) + list(file_ids_map.values())
                except Exception as e:
                    error_msg = str(e)
                    await cleanup_setup_context()

                    async def error_generator():
                        yield (
                            "data: "
                            + json.dumps({"error": f"Error downloading file from provided urls: {error_msg}"})
                            + "\n\n"
                        )
                        yield "event: end\ndata: [DONE]\n\n"

                    return StreamingResponse(
                        error_generator(),
                        media_type="text/event-stream",
                        headers={
                            "Cache-Control": "no-cache",
                            "Connection": "keep-alive",
                            "X-Accel-Buffering": "no",
                        },
                    )
            await attach_persistent_mcp_servers(agency_instance)
        except Exception:
            await cleanup_setup_context()
            raise

        # Generate unique run_id for this streaming session
        run_id = str(uuid.uuid4())
        cleanup_lock = asyncio.Lock()
        cleanup_completed = False

        async def cleanup_stream_context() -> None:
            nonlocal cleanup_completed
            async with cleanup_lock:
                if cleanup_completed:
                    return
                cleanup_completed = True
                await override_session.cleanup()

        async def event_generator():
            # Capture initial message count to identify new messages
            initial_message_count = len(agency_instance.thread_manager.get_all_messages())

            stream = None
            active_run: ActiveRun | None = None
            try:
                stream = agency_instance.get_response_stream(
                    message=request.message,
                    recipient_agent=request.recipient_agent,
                    context_override=request.user_context,
                    additional_instructions=request.additional_instructions,
                    file_ids=combined_file_ids,
                )

                active_run = ActiveRun(
                    stream=stream,
                    agency=agency_instance,
                    initial_message_count=initial_message_count,
                )
                await run_registry.register(run_id, active_run)

                # Now send run_id - client can safely call cancel endpoint
                yield f"event: meta\ndata: {json.dumps({'run_id': run_id})}\n\n"

                async for event in stream:
                    # Check if client disconnected (tab close, refresh, etc.)
                    if await http_request.is_disconnected():
                        logger.info(f"Client disconnected, cancelling run {run_id}")
                        stream.cancel(mode="immediate")
                        if active_run is not None:
                            active_run.cancelled = True
                            active_run.cancel_mode = "immediate"
                        break

                    try:
                        data = serialize(event)
                        yield "data: " + json.dumps({"data": data}) + "\n\n"
                    except Exception as e:
                        yield "data: " + json.dumps({"error": f"Failed to serialize event: {e}"}) + "\n\n"

            except Exception as exc:
                if isinstance(exc, OutputGuardrailTripwireTriggered):
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "error": "Guardrail OutputGuardrail triggered tripwire: "
                                + str(exc.guardrail_result.output.output_info)
                            }
                        )
                        + "\n\n"
                    )
                else:
                    yield "data: " + json.dumps({"error": str(exc)}) + "\n\n"
            finally:
                # Ensure registry cleanup happens even if serialization fails (Fix #10)
                try:
                    # Get messages generated before cancel/completion
                    all_messages = agency_instance.thread_manager.get_all_messages()
                    new_messages = all_messages[initial_message_count:]
                    # Remove duplicates, filter unwanted types, and remove orphaned tool calls/outputs
                    filtered_messages = MessageFilter.remove_duplicates(new_messages)
                    filtered_messages = MessageFilter.filter_messages(filtered_messages)
                    filtered_messages = MessageFilter.remove_orphaned_messages(filtered_messages)
                    filtered_messages = _normalize_new_messages_for_client(filtered_messages)

                    # Extract usage from final result
                    final_result = stream.final_result if stream else None
                    usage_stats = extract_usage_from_run_result(final_result)
                    if usage_stats:
                        # Calculate cost - model_name is auto-extracted from run_result._main_agent_model
                        usage_stats = calculate_usage_with_cost(usage_stats, run_result=final_result)

                    # Build result with new messages
                    result = {"new_messages": filtered_messages, "run_id": run_id}
                    if active_run is not None and active_run.cancelled:
                        result["cancelled"] = True
                    if request.file_urls is not None and file_ids_map is not None:
                        result["file_ids_map"] = file_ids_map
                    if request.generate_chat_name:
                        try:
                            result["chat_name"] = await generate_chat_name(
                                filtered_messages,
                                openai_client=request_upload_client,
                            )
                        except Exception as e:
                            logger.error(f"Error generating chat name: {e}")
                    if usage_stats:
                        result["usage"] = usage_stats.to_dict()

                    yield "event: messages\ndata: " + json.dumps(result) + "\n\n"
                    yield "event: end\ndata: [DONE]\n\n"
                except Exception as e:
                    logger.error(f"Error building final response: {e}")
                    yield "data: " + json.dumps({"error": f"Error building response: {e}"}) + "\n\n"
                    yield "event: end\ndata: [DONE]\n\n"
                finally:
                    await run_registry.finish(run_id)
                    await cleanup_stream_context()

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
            background=BackgroundTask(cleanup_stream_context),
        )

    return handler


# Cancel streaming endpoint
def make_cancel_endpoint(request_model, verify_token, run_registry: ActiveRunRegistry):
    """Create a cancel endpoint that stops an active streaming run.

    Returns the messages generated before cancellation.
    """

    async def handler(request: request_model, token: str = Depends(verify_token)):
        run_id = request.run_id
        cancel_mode = request.cancel_mode or "immediate"

        active_run = await run_registry.mark_cancelled(run_id, cancel_mode)
        if active_run is None:
            raise HTTPException(
                status_code=404,
                detail=f"Run '{run_id}' not found or already completed",
            )

        # Mark as cancelled and call cancel on the stream
        active_run.stream.cancel(mode=cancel_mode)
        logger.info(f"Cancelled run {run_id} via cancel endpoint (mode={cancel_mode})")

        # Wait for the streaming worker to finish draining events
        timed_out = False
        try:
            await asyncio.wait_for(active_run.done_event.wait(), timeout=60)
        except TimeoutError:
            logger.warning("Timed out waiting for run %s to finish cancellation (mode=%s)", run_id, cancel_mode)
            timed_out = True
        # Get messages generated before cancel
        all_messages = active_run.agency.thread_manager.get_all_messages()
        new_messages = all_messages[active_run.initial_message_count :]
        # Remove duplicates, filter unwanted types, and remove orphaned tool calls/outputs
        filtered_messages = MessageFilter.remove_duplicates(new_messages)
        filtered_messages = MessageFilter.filter_messages(filtered_messages)
        filtered_messages = MessageFilter.remove_orphaned_messages(filtered_messages)
        filtered_messages = _normalize_new_messages_for_client(filtered_messages)

        return {
            "ok": not timed_out,
            "run_id": run_id,
            "cancelled": not timed_out,
            "cancel_mode": cancel_mode,
            "new_messages": filtered_messages,
            "timed_out": timed_out,
        }

    return handler


def make_agui_chat_endpoint(
    request_model,
    agency_factory: Callable[..., Agency],
    verify_token,
    allowed_local_dirs: Sequence[str | Path] | None = None,
):
    async def handler(request: request_model, token: str = Depends(verify_token)):
        """Accepts AG-UI `RunAgentInput`, returns an AG-UI event stream."""

        encoder = EventEncoder()

        combined_file_ids = list(request.file_ids or []) if getattr(request, "file_ids", None) else []

        if request.chat_history is not None:
            # Chat history is now a flat list
            def load_callback() -> list:
                return request.chat_history

        elif request.messages is not None:
            # Pull the default agent from the agency
            agency = agency_factory()
            default_agent = agency.entry_points[0]

            # Convert AG-UI messages to flat chat history with metadata
            def load_callback() -> list:
                agui_messages = AguiAdapter.agui_messages_to_chat_history(request.messages)
                # Add agency metadata to each message
                for msg in agui_messages:
                    if "agent" not in msg:
                        msg["agent"] = default_agent.name
                    if "callerAgent" not in msg:
                        msg["callerAgent"] = None
                    if "timestamp" not in msg:
                        msg["timestamp"] = int(time.time() * 1000)
                return agui_messages

        else:

            def load_callback() -> list:
                return []

        # Choose / build an agent – here we just create a demo agent each time.
        agency = agency_factory(load_threads_callback=load_callback)
        override_policy = RequestOverridePolicy(request.client_config)
        override_session = _RequestOverrideSession(agency=agency, policy=override_policy)
        request_upload_client: AsyncOpenAI | None = None

        async def cleanup_setup_context() -> None:
            await override_session.cleanup()

        try:
            await override_session.acquire()

            request_upload_client = _build_file_upload_client(agency, request.client_config, recipient_agent=None)
            if getattr(request, "file_urls", None):
                try:
                    file_ids_map = await upload_from_urls(
                        request.file_urls,
                        allowed_local_dirs=allowed_local_dirs,
                        openai_client=request_upload_client,
                    )
                    combined_file_ids = combined_file_ids + list(file_ids_map.values())
                except Exception as exc:
                    error_message = f"Error downloading file from provided urls: {exc}"
                    await cleanup_setup_context()
                    run_started = RunStartedEvent(
                        type=EventType.RUN_STARTED,
                        thread_id=request.thread_id,
                        run_id=request.run_id,
                    )
                    run_error = RunErrorEvent(type=EventType.RUN_ERROR, message=error_message)
                    run_finished = RunFinishedEvent(
                        type=EventType.RUN_FINISHED,
                        thread_id=request.thread_id,
                        run_id=request.run_id,
                    )
                    return StreamingResponse(
                        (encoder.encode(event) for event in (run_started, run_error, run_finished)),
                        media_type=encoder.get_content_type(),
                    )
            await attach_persistent_mcp_servers(agency)
        except Exception:
            await cleanup_setup_context()
            raise

        cleanup_lock = asyncio.Lock()
        cleanup_completed = False

        async def cleanup_stream_context() -> None:
            nonlocal cleanup_completed
            async with cleanup_lock:
                if cleanup_completed:
                    return
                cleanup_completed = True
                await override_session.cleanup()

        async def event_generator() -> AsyncGenerator[str]:
            # Emit RUN_STARTED first.
            yield encoder.encode(
                RunStartedEvent(
                    type=EventType.RUN_STARTED,
                    thread_id=request.thread_id,
                    run_id=request.run_id,
                )
            )

            try:
                # Create AguiAdapter instance with clean state for this request
                agui_adapter = AguiAdapter()

                # Store in dict format to avoid converting to classes
                snapshot_messages = [message.model_dump() for message in request.messages]
                async for event in agency.get_response_stream(
                    message=request.messages[-1].content,
                    context_override=request.user_context,
                    additional_instructions=request.additional_instructions,
                    file_ids=combined_file_ids or None,
                ):
                    agui_event = agui_adapter.openai_to_agui_events(
                        event,
                        run_id=request.run_id,
                    )
                    if agui_event:
                        agui_events = agui_event if isinstance(agui_event, list) else [agui_event]
                        for agui_evt in agui_events:
                            if isinstance(agui_evt, MessagesSnapshotEvent):
                                snapshot_messages.append(agui_evt.messages[0].model_dump())
                                yield encoder.encode(
                                    MessagesSnapshotEvent(type=EventType.MESSAGES_SNAPSHOT, messages=snapshot_messages)
                                )
                            else:
                                yield encoder.encode(agui_evt)

                yield encoder.encode(
                    RunFinishedEvent(
                        type=EventType.RUN_FINISHED,
                        thread_id=request.thread_id,
                        run_id=request.run_id,
                    )
                )

            except Exception as exc:
                # Surface error as AG-UI event so the frontend can react.
                tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                error_message = f"{str(exc)}\n\nTraceback:\n{tb_str}"
                yield encoder.encode(RunErrorEvent(type=EventType.RUN_ERROR, message=error_message))
            finally:
                await cleanup_stream_context()

        return StreamingResponse(
            event_generator(),
            media_type=encoder.get_content_type(),
            background=BackgroundTask(cleanup_stream_context),
        )

    return handler


def _normalize_new_messages_for_client(messages: list[TResponseInputItem]) -> list[TResponseInputItem]:
    """Normalize server-side message items for client consumption.

    LiteLLM / Chat Completions integrations can emit `id=FAKE_RESPONSES_ID` for multiple distinct
    items. Client code commonly keys and merges by `id`, so rewrite placeholder ids into stable,
    unique ids within the final `new_messages` payload while preserving `call_id` linking for tool
    calls.
    """
    normalizer = StreamIdNormalizer()
    return normalizer.normalize_message_dicts(messages)


def make_metadata_endpoint(
    agency_metadata: dict,
    verify_token,
    allowed_local_dirs: Sequence[str | Path] | None = None,
):
    async def handler(token: str = Depends(verify_token)):
        metadata_with_version = dict(agency_metadata)
        agency_swarm_version = _get_agency_swarm_version()
        if agency_swarm_version is not None:
            metadata_with_version["agency_swarm_version"] = agency_swarm_version
        # Always include so clients can tell if local file access is enabled and what paths are allowed.
        if allowed_local_dirs is None:
            metadata_with_version["allowed_local_file_dirs"] = None
        else:
            metadata_with_version["allowed_local_file_dirs"] = get_allowed_dirs_for_metadata(allowed_local_dirs)
        return metadata_with_version

    return handler


def make_logs_endpoint(request_model, logs_dir: str, verify_token):
    """Create a logs endpoint handler following the same pattern as other endpoints."""

    async def handler(request: request_model, token: str = Depends(verify_token)):
        return await get_logs_endpoint_impl(request.log_id, logs_dir)

    return handler


async def exception_handler(request, exc):
    error_message = str(exc)
    if isinstance(exc, tuple):
        error_message = str(exc[1]) if len(exc) > 1 else str(exc[0])
    return JSONResponse(status_code=500, content={"error": error_message})


async def generate_chat_name(
    new_messages: list[TResponseInputItem],
    openai_client: AsyncOpenAI | None = None,
):
    client = openai_client or get_default_openai_client() or AsyncOpenAI()

    class ResponseFormat(BaseModel):
        chat_name: str = Field(description="A fitting name for the provided chat history.")

    @output_guardrail  # type: ignore[arg-type]
    async def response_content_guardrail(
        context: RunContextWrapper, agent: Agent, response_text: str | type[BaseModel]
    ) -> GuardrailFunctionOutput:
        tripwire_triggered = False
        output_info = ""

        chat_name = response_text.chat_name if isinstance(response_text, ResponseFormat) else str(response_text)

        if len(chat_name.split(" ")) < 2 or len(chat_name.split(" ")) > 6:
            tripwire_triggered = True
            output_info = "The name should contain between 2 and 6 words"

        return GuardrailFunctionOutput(
            output_info=output_info,
            tripwire_triggered=tripwire_triggered,
        )

    formatted_messages = str(MessageFormatter.strip_agency_metadata(new_messages))  # type: ignore[arg-type]
    if len(formatted_messages) > 1000:
        formatted_messages = "HISTORY TRUNCATED TO 1000 CHARACTERS:\n" + formatted_messages[:1000]

    model = OpenAIResponsesModel(model="gpt-5-nano", openai_client=client)

    name_agent = Agent(
        name="NameGenerator",
        model=model,
        instructions=(
            """
You are a helpful assistant that generates a human-friendly title for a conversation.
You will receive a list of messages where the first one is the user input and the rest are
related to the assistant response.
Rules:
- Prioritize the user's first message; use later turns only to disambiguate
- 2-6 words, Title Case
- No punctuation except spaces; no emojis, quotes, model/tool names, or trailing period
- Output only the title text (no explanations)
- If the first user message is generic (e.g., “hi”), use the best available intent from the rest of the messages.
- If you lack context of the user input (continuation of an ongoing conversation), derive it from agent's response.
"""
        ),
        output_type=ResponseFormat,
        validation_attempts=3,
        output_guardrails=[response_content_guardrail],
    )

    agency = Agency(name_agent)

    response = await agency.get_response(formatted_messages)

    return response.final_output.chat_name


def _get_agency_swarm_version() -> str | None:
    """Return the installed agency-swarm version, if available."""

    try:
        return metadata.version("agency-swarm")
    except metadata.PackageNotFoundError:
        logger.debug("agency-swarm package metadata not found; returning no version")
        return None


def _build_openai_client_for_agent(agent: Agent, config: ClientConfig) -> AsyncOpenAI | None:
    """Build an AsyncOpenAI client by layering config over existing defaults.

    Priority:
    - explicit values from `config` win
    - otherwise fall back to the agent's existing OpenAI client (if any)
    - otherwise fall back to the global default OpenAI client (if any)
    - otherwise:
      - if `config` only includes default_headers, skip client replacement (no baseline client to copy)
      - else create a fresh AsyncOpenAI() using environment variables/request overrides
    """
    base_client = _get_openai_client_from_agent(agent) or get_default_openai_client()

    if base_client is None:
        if config.api_key is None and config.base_url is None:
            return None
        # Allow request-provided api_key/base_url to work even when the server has no OPENAI_API_KEY.
        return AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            default_headers=config.default_headers,
        )

    # Only override the values that are explicitly provided in `config`.
    # OpenAI's `copy()` also handles merging default headers correctly.
    return base_client.copy(
        api_key=config.api_key,
        base_url=config.base_url,
        default_headers=config.default_headers,
    )


def _build_request_scoped_openai_client(agent: Agent, config: ClientConfig) -> AsyncOpenAI | None:
    """Build a request-scoped AsyncOpenAI client for direct agent client access paths."""
    base_client = (
        _get_openai_client_from_agent(agent) or getattr(agent, "_openai_client", None) or get_default_openai_client()
    )
    if base_client is None:
        # No existing client to copy from. Without an explicit api_key we can't build one safely.
        if config.api_key is None:
            return None
        return AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            default_headers=config.default_headers,
        )

    return base_client.copy(
        api_key=config.api_key,
        base_url=config.base_url,
        default_headers=config.default_headers,
    )


def _apply_request_scoped_openai_clients_to_agent(agent: Agent, config: ClientConfig) -> None:
    """Apply request-scoped async+sync OpenAI clients used by attachment/file managers."""
    async_client = _build_request_scoped_openai_client(agent, config)
    if async_client is None:
        return

    agent._openai_client = async_client
    sync_base_url = str(async_client.base_url) if getattr(async_client, "base_url", None) is not None else None
    sync_headers_raw = async_client.default_headers
    sync_headers: dict[str, str] | None = None
    if sync_headers_raw is not None:
        # AsyncOpenAI headers may include non-string sentinel values; sync client expects plain str headers.
        sync_headers = {key: value for key, value in sync_headers_raw.items() if isinstance(value, str)}
    agent._openai_client_sync = OpenAI(
        api_key=async_client.api_key,
        base_url=sync_base_url,
        default_headers=sync_headers,
    )


def _apply_default_headers_to_agent_model_settings(agent: Agent, headers: dict[str, str]) -> None:
    """Merge request headers into this agent's ModelSettings.extra_headers."""
    if not headers:
        return
    current: ModelSettings = getattr(agent, "model_settings", None) or ModelSettings()
    existing = dict(current.extra_headers or {})
    merged = {**existing, **headers}
    # ModelSettings is a dataclass (agents==0.6.4), so updating requires replacement.
    current.extra_headers = merged
    agent.model_settings = current


def _is_litellm_model(model_name: str) -> bool:
    """Check if a model name is a LiteLLM model (uses litellm/ prefix)."""
    return model_name.startswith("litellm/")


def _is_openai_model_name(model_name: str) -> bool:
    """Return True if a model name should be treated as OpenAI-compatible.

    The Agents SDK's MultiProvider treats:
    - no prefix (e.g. "gpt-4o") as OpenAI
    - "openai/<model>" as OpenAI

    For any other prefix (e.g. "anthropic/<model>"), we should NOT wrap into
    OpenAIResponsesModel, since that would route through the OpenAI client.
    """
    if "/" not in model_name:
        return True
    prefix, _rest = model_name.split("/", 1)
    return prefix == "openai"


def _get_model_name_for_override_logging(agent: Agent) -> str | None:
    """Return a human-friendly model identifier for override logs."""
    model = agent.model
    if isinstance(model, str):
        return model
    if isinstance(model, OpenAIResponsesModel | OpenAIChatCompletionsModel):
        return model.model
    if isinstance(model, Model):
        model_name = getattr(model, "model", None)
        if isinstance(model_name, str):
            return model_name
    return None


def _agent_supports_openai_client_override(agent: Agent) -> bool:
    """Return True only when request OpenAI client overrides are applicable."""
    model_name = _get_model_name_for_override_logging(agent)
    if model_name is None:
        return False
    return _is_openai_model_name(model_name)


def _log_unsupported_client_override(agent: Agent) -> None:
    model_name = _get_model_name_for_override_logging(agent)
    if model_name is not None:
        logger.warning(
            "Skipping client_config for agent '%s': custom model '%s' is not supported for "
            "client override (only OpenAI models or 'litellm/' models are supported)",
            agent.name,
            model_name,
        )
        return

    logger.warning(
        "Cannot apply client config to agent '%s': unsupported model type %s",
        agent.name,
        type(agent.model).__name__,
    )


def _apply_client_to_agent(agent: Agent, client: AsyncOpenAI | None, config: ClientConfig) -> None:
    """Apply a custom OpenAI client to an agent's model.

    For OpenAI models, wraps them in OpenAIResponsesModel with the custom client.
    For LiteLLM models, creates a new LitellmModel with base_url and api_key from config.
    """
    model = agent.model
    has_litellm_overrides = config.base_url is not None or config.api_key is not None or config.litellm_keys is not None

    if isinstance(model, str):
        if _is_litellm_model(model):
            if has_litellm_overrides:
                _apply_litellm_config(agent, model, config)
        elif not _is_openai_model_name(model):
            logger.warning(
                "Skipping client_config for agent '%s': custom model '%s' is not supported for "
                "client override (only OpenAI models or 'litellm/' models are supported)",
                agent.name,
                model,
            )
        else:
            # String model name - wrap in OpenAIResponsesModel with custom client
            if client is None:
                return
            agent.model = OpenAIResponsesModel(model=model, openai_client=client)
    elif isinstance(model, OpenAIResponsesModel):
        if _is_litellm_model(model.model):
            if has_litellm_overrides:
                _apply_litellm_config(agent, model.model, config)
        elif not _is_openai_model_name(model.model):
            logger.warning(
                "Skipping client_config for agent '%s': custom model '%s' is not supported for "
                "client override (only OpenAI models or 'litellm/' models are supported)",
                agent.name,
                model.model,
            )
        else:
            # Create new model instance with custom client, preserving model name
            if client is None:
                return
            agent.model = OpenAIResponsesModel(model=model.model, openai_client=client)
    elif isinstance(model, OpenAIChatCompletionsModel):
        if _is_litellm_model(model.model):
            if has_litellm_overrides:
                _apply_litellm_config(agent, model.model, config)
        elif not _is_openai_model_name(model.model):
            logger.warning(
                "Skipping client_config for agent '%s': custom model '%s' is not supported for "
                "client override (only OpenAI models or 'litellm/' models are supported)",
                agent.name,
                model.model,
            )
        else:
            # Create new model instance with custom client, preserving model name
            if client is None:
                return
            agent.model = OpenAIChatCompletionsModel(model=model.model, openai_client=client)
    elif _LITELLM_AVAILABLE and LitellmModel is not None and isinstance(model, LitellmModel):
        if has_litellm_overrides:
            # Preserve existing settings unless explicitly overridden.
            base_url = config.base_url if config.base_url is not None else model.base_url
            api_key = _resolve_litellm_api_key(model.model, config, existing_api_key=model.api_key)
            agent.model = LitellmModel(model=model.model, base_url=base_url, api_key=api_key)
    elif isinstance(model, Model):
        # For other Model types, try to extract and wrap with OpenAIResponsesModel
        model_name = getattr(model, "model", None)
        if isinstance(model_name, str):
            if _is_litellm_model(model_name):
                if has_litellm_overrides:
                    _apply_litellm_config(agent, model_name, config)
            elif not _is_openai_model_name(model_name):
                logger.warning(
                    "Skipping client_config for agent '%s': custom model '%s' is not supported for "
                    "client override (only OpenAI models or 'litellm/' models are supported)",
                    agent.name,
                    model_name,
                )
            else:
                if client is None:
                    return
                agent.model = OpenAIResponsesModel(model=model_name, openai_client=client)
        else:
            logger.warning(
                f"Cannot apply client config to agent '{agent.name}': unsupported model type {type(model).__name__}"
            )
    else:
        logger.warning(
            f"Cannot apply client config to agent '{agent.name}': unsupported model type {type(model).__name__}"
        )


def _agent_uses_litellm(agent: Agent) -> bool:
    model = agent.model
    if isinstance(model, str):
        return _is_litellm_model(model)
    if isinstance(model, OpenAIResponsesModel | OpenAIChatCompletionsModel):
        return _is_litellm_model(model.model)
    if _LITELLM_AVAILABLE and LitellmModel is not None and isinstance(model, LitellmModel):
        return True
    if isinstance(model, Model):
        model_name = getattr(model, "model", None)
        return isinstance(model_name, str) and _is_litellm_model(model_name)
    return False


def _get_litellm_provider(model_name: str) -> str | None:
    """Extract provider name from a LiteLLM model string.

    Examples:
        "litellm/anthropic/claude-sonnet-4" -> "anthropic"
        "anthropic/claude-sonnet-4" -> "anthropic"
        "claude-sonnet-4" -> None
    """
    # Strip litellm/ prefix if present
    name = model_name[8:] if model_name.startswith("litellm/") else model_name

    # Provider is the first segment before /
    if "/" in name:
        return name.split("/")[0]
    return None


def _is_openai_based_litellm_provider(provider: str | None) -> bool:
    # LiteLLM treats openai-like providers differently; allow request api_key as a fallback there.
    # For non-OpenAI providers (anthropic/gemini/etc), prefer env unless litellm_keys is provided.
    return provider in {None, "openai", "azure", "azure_ai", "openai_compatible"}


def _resolve_litellm_api_key(
    model_name: str,
    config: ClientConfig,
    existing_api_key: str | None = None,
) -> str | None:
    provider = _get_litellm_provider(model_name)

    # Prefer provider-specific keys when provided.
    if config.litellm_keys:
        if provider:
            for key, value in config.litellm_keys.items():
                key_str = key.value if hasattr(key, "value") else str(key)
                if key_str == provider:
                    return value
        # Provider missing in litellm_keys:
        # - For openai-based providers, allow falling back to config.api_key.
        # - Otherwise keep existing (or env if None).
        if _is_openai_based_litellm_provider(provider):
            return config.api_key if config.api_key is not None else existing_api_key
        return existing_api_key

    # No litellm_keys provided: only use config.api_key for openai-based providers.
    if _is_openai_based_litellm_provider(provider):
        return config.api_key if config.api_key is not None else existing_api_key
    return existing_api_key


def _apply_litellm_config(agent: Agent, model_name: str, config: ClientConfig) -> None:
    """Apply config to a LiteLLM model by creating a new LitellmModel instance."""
    if not _LITELLM_AVAILABLE or LitellmModel is None:
        logger.warning(
            f"Cannot apply client config to agent '{agent.name}': LiteLLM model "
            f"('{model_name}') requires openai-agents[litellm] to be installed"
        )
        return

    # Strip the 'litellm/' prefix to get the actual model identifier
    actual_model = model_name[8:] if model_name.startswith("litellm/") else model_name

    api_key = _resolve_litellm_api_key(model_name, config, existing_api_key=None)

    agent.model = LitellmModel(
        model=actual_model,
        base_url=config.base_url,
        api_key=api_key,
    )


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
        )
    return snapshot


def _restore_agency_state(
    agency: Agency,
    snapshot: _AgencyStateSnapshot,
) -> None:
    """Restore agent model/model_settings/OpenAI clients after a request override."""
    for name, (model, model_settings, openai_client, openai_client_sync) in snapshot.items():
        agent = agency.agents.get(name)
        if agent is None:
            continue
        agent.model = model
        if model_settings is None:
            agent.model_settings = cast(ModelSettings, None)
        else:
            agent.model_settings = model_settings
        agent._openai_client = openai_client
        agent._openai_client_sync = openai_client_sync


async def _get_agency_request_state(agency: Agency) -> _AgencyRequestState:
    """Return per-agency request coordination state for the current event loop."""
    loop = asyncio.get_running_loop()
    with _AGENCY_REQUEST_STATES_GUARD:
        per_loop = _AGENCY_REQUEST_STATES.get(agency)
        if per_loop is None:
            per_loop = {}
            _AGENCY_REQUEST_STATES[agency] = per_loop

        # Drop closed-loop state to avoid unbounded growth in long-lived processes.
        closed_loops = [existing_loop for existing_loop in per_loop if existing_loop.is_closed()]
        for closed_loop in closed_loops:
            per_loop.pop(closed_loop, None)

        active_loops = [existing_loop for existing_loop in per_loop if not existing_loop.is_closed()]
        if active_loops and loop not in per_loop:
            logger.warning(
                "Agency '%s' is being reused across event loops; request coordination remains per-loop only.",
                getattr(agency, "name", agency.__class__.__name__),
            )

        existing = per_loop.get(loop)
        if existing is not None:
            return existing

        created = _AgencyRequestState()
        per_loop[loop] = created
        return created


async def _acquire_agency_request_lease(agency: Agency, is_override: bool) -> _AgencyRequestLease:
    """Acquire a regular or override lease for a request."""
    state = await _get_agency_request_state(agency)
    async with state.state_changed:
        if is_override:
            state.pending_overrides += 1
            try:
                await state.state_changed.wait_for(
                    lambda: not state.override_active and state.active_regular_requests == 0
                )
                state.override_active = True
            finally:
                state.pending_overrides -= 1
                state.state_changed.notify_all()
        else:
            # Once an override is queued, block new regular requests so the override
            # can run as soon as in-flight regular work drains.
            await state.state_changed.wait_for(lambda: not state.override_active and state.pending_overrides == 0)
            state.active_regular_requests += 1
    return _AgencyRequestLease(state=state, is_override=is_override)


async def _release_agency_request_lease(lease: _AgencyRequestLease) -> None:
    """Release a previously acquired request lease."""
    state = lease.state
    async with state.state_changed:
        if lease.is_override:
            state.override_active = False
        else:
            state.active_regular_requests -= 1
        state.state_changed.notify_all()

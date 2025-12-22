import asyncio
import contextlib
import json
import logging
import time
import traceback
import uuid
from collections.abc import AsyncGenerator, Callable, Sequence
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any

from ag_ui.core import BaseEvent, EventType, MessagesSnapshotEvent, RunErrorEvent, RunFinishedEvent, RunStartedEvent
from ag_ui.encoder import EventEncoder
from agents import Model, OpenAIChatCompletionsModel, OpenAIResponsesModel, TResponseInputItem, output_guardrail
from agents.exceptions import OutputGuardrailTripwireTriggered
from agents.models._openai_shared import get_default_openai_client
from agents.models.fake_id import FAKE_RESPONSES_ID

# LiteLLM is optional - only available if openai-agents[litellm] is installed
try:
    from agents.extensions.models.litellm_model import LitellmModel

    _LITELLM_AVAILABLE = True
except ImportError:
    _LITELLM_AVAILABLE = False
    LitellmModel = None  # type: ignore[misc, assignment]
from fastapi import Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from agency_swarm import (
    Agency,
    Agent,
    GuardrailFunctionOutput,
    RunContextWrapper,
)
from agency_swarm.agent.execution_stream_response import StreamingRunResponse
from agency_swarm.integrations.fastapi_utils.file_handler import upload_from_urls
from agency_swarm.integrations.fastapi_utils.logging_middleware import get_logs_endpoint_impl
from agency_swarm.integrations.fastapi_utils.oauth_support import (
    FastAPIOAuthConfig,
    FastAPIOAuthRuntime,
    has_hosted_mcp_tools_missing_authorization,
    is_oauth_server,
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
    if config.base_url is None and config.api_key is None and config.litellm_keys is None:
        return  # Nothing to override

    # Create custom client with overrides
    client = AsyncOpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
    )

    # Apply to all agents in the agency
    for agent in agency.agents.values():
        _apply_client_to_agent(agent, client, config)


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


def _apply_client_to_agent(agent: Agent, client: AsyncOpenAI, config: ClientConfig) -> None:
    """Apply a custom OpenAI client to an agent's model.

    For OpenAI models, wraps them in OpenAIResponsesModel with the custom client.
    For LiteLLM models, creates a new LitellmModel with base_url and api_key from config.
    """
    model = agent.model

    if isinstance(model, str):
        if _is_litellm_model(model):
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
            agent.model = OpenAIResponsesModel(model=model, openai_client=client)
    elif isinstance(model, OpenAIResponsesModel):
        if _is_litellm_model(model.model):
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
            agent.model = OpenAIResponsesModel(model=model.model, openai_client=client)
    elif isinstance(model, OpenAIChatCompletionsModel):
        if _is_litellm_model(model.model):
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
            agent.model = OpenAIChatCompletionsModel(model=model.model, openai_client=client)
    elif _LITELLM_AVAILABLE and LitellmModel is not None and isinstance(model, LitellmModel):
        # Already a LitellmModel instance - create new one with config
        agent.model = LitellmModel(
            model=model.model,
            base_url=config.base_url,
            api_key=config.api_key,
        )
    elif isinstance(model, Model):
        # For other Model types, try to extract and wrap with OpenAIResponsesModel
        model_name = getattr(model, "model", None)
        if isinstance(model_name, str):
            if _is_litellm_model(model_name):
                _apply_litellm_config(agent, model_name, config)
            elif not _is_openai_model_name(model_name):
                logger.warning(
                    "Skipping client_config for agent '%s': custom model '%s' is not supported for "
                    "client override (only OpenAI models or 'litellm/' models are supported)",
                    agent.name,
                    model_name,
                )
            else:
                agent.model = OpenAIResponsesModel(model=model_name, openai_client=client)
        else:
            logger.warning(
                f"Cannot apply client config to agent '{agent.name}': unsupported model type {type(model).__name__}"
            )
    else:
        logger.warning(
            f"Cannot apply client config to agent '{agent.name}': unsupported model type {type(model).__name__}"
        )


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

    # Determine which API key to use:
    # 1. Provider-specific key from litellm_keys (if available)
    # 2. Fall back to generic api_key
    # 3. None (LiteLLM will use environment variables)
    api_key = config.api_key
    if config.litellm_keys:
        provider = _get_litellm_provider(model_name)
        if provider:
            # litellm_keys uses LlmProviders enum as keys (when litellm installed)
            # Look up by iterating since keys may be enum instances
            for key, value in config.litellm_keys.items():
                # Compare by value (works for both enum and string keys)
                key_str = key.value if hasattr(key, "value") else str(key)
                if key_str == provider:
                    api_key = value
                    break

    agent.model = LitellmModel(
        model=actual_model,
        base_url=config.base_url,
        api_key=api_key,
    )


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


def _set_oauth_user_context(user_id: str | None) -> None:
    """Set the OAuth user ID contextvar for per-user token isolation.

    Must be called BEFORE MCP server connections are established.
    """
    if user_id is None:
        return
    try:
        from agency_swarm.mcp.oauth import set_oauth_user_id

        set_oauth_user_id(user_id)
    except ImportError:
        pass  # OAuth extras not installed


def _prepare_oauth_runtime(
    agency_instance: Agency,
    oauth_runtime: FastAPIOAuthRuntime | None,
    user_id: str | None,
) -> FastAPIOAuthRuntime | None:
    """Attach per-request OAuth helpers and propagate user_id.

    This sets the user_id in both the agency's user_context (for run-time hooks)
    and the OAuth contextvar (for token storage during MCP server connection).
    """
    # Always set OAuth user context for token isolation, even without oauth_runtime
    _set_oauth_user_context(user_id)

    agency_instance.user_context = dict(getattr(agency_instance, "user_context", {}))
    if user_id is not None:
        agency_instance.user_context["user_id"] = user_id

    if oauth_runtime is None:
        return None

    for agent in agency_instance.agents.values():
        oauth_runtime.install_handler_factory(agent)
    return oauth_runtime


def _has_oauth_servers(agency_instance: Agency) -> bool:
    agents_map = getattr(agency_instance, "agents", {})
    if not isinstance(agents_map, dict):
        return False
    for agent in agents_map.values():
        servers = getattr(agent, "mcp_servers", None)
        if isinstance(servers, list) and any(is_oauth_server(srv) for srv in servers):
            return True
    return False


# Non‑streaming response endpoint
def make_response_endpoint(
    request_model,
    agency_factory: Callable[..., Agency],
    verify_token,
    allowed_local_dirs: Sequence[str | Path] | None = None,
    oauth_config: FastAPIOAuthConfig | None = None,
):
    user_header = oauth_config.user_header if oauth_config else "X-User-Id"

    async def handler(
        request: request_model,
        token: str = Depends(verify_token),
        user_id: str | None = Header(default=None, alias=user_header),
    ):
        if request.chat_history is not None:
            # Chat history is now a flat list
            def load_callback() -> list:
                return request.chat_history
        else:

            def load_callback() -> list:
                return []

        combined_file_ids = request.file_ids
        file_ids_map = None
        if request.file_urls is not None:
            try:
                file_ids_map = await upload_from_urls(request.file_urls, allowed_local_dirs=allowed_local_dirs)
                combined_file_ids = (combined_file_ids or []) + list(file_ids_map.values())
            except Exception as e:
                return {"error": f"Error downloading file from provided urls: {e}"}

        oauth_runtime = None
        if oauth_config:
            oauth_runtime = FastAPIOAuthRuntime(oauth_config.registry, user_id, timeout=oauth_config.timeout)

        agency_instance = agency_factory(load_threads_callback=load_callback)

        # Apply custom OpenAI client configuration if provided
        if request.client_config is not None:
            apply_openai_client_config(agency_instance, request.client_config)

        if oauth_runtime and (
            _has_oauth_servers(agency_instance) or has_hosted_mcp_tools_missing_authorization(agency_instance)
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "OAuth-enabled MCP servers and hosted MCP tools require /get_response_stream for redirect events"
                ),
            )
        oauth_runtime = _prepare_oauth_runtime(agency_instance, oauth_runtime, user_id)
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
                result["chat_name"] = await generate_chat_name(filtered_messages)
            except Exception as e:
                # Do not add errors to the result as they might be mistaken for chat name
                logger.error(f"Error generating chat name: {e}")
        return result

    return handler


# Streaming SSE endpoint
def make_stream_endpoint(
    request_model,
    agency_factory: Callable[..., Agency],
    verify_token,
    run_registry: ActiveRunRegistry,
    allowed_local_dirs: Sequence[str | Path] | None = None,
    oauth_config: FastAPIOAuthConfig | None = None,
):
    user_header = oauth_config.user_header if oauth_config else "X-User-Id"

    async def handler(
        http_request: Request,
        request: request_model,
        token: str = Depends(verify_token),
        user_id: str | None = Header(default=None, alias=user_header),
    ):
        if request.chat_history is not None:
            # Chat history is now a flat list
            def load_callback() -> list:
                return request.chat_history
        else:

            def load_callback() -> list:
                return []

        combined_file_ids = request.file_ids
        file_ids_map = None
        if request.file_urls is not None:
            try:
                file_ids_map = await upload_from_urls(request.file_urls, allowed_local_dirs=allowed_local_dirs)
                combined_file_ids = (combined_file_ids or []) + list(file_ids_map.values())
            except Exception as e:
                error_msg = str(e)

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

        oauth_runtime = None
        if oauth_config:
            oauth_runtime = FastAPIOAuthRuntime(oauth_config.registry, user_id, timeout=oauth_config.timeout)

        agency_instance = agency_factory(load_threads_callback=load_callback)

        # Apply custom OpenAI client configuration if provided
        if request.client_config is not None:
            apply_openai_client_config(agency_instance, request.client_config)

        oauth_runtime = _prepare_oauth_runtime(agency_instance, oauth_runtime, user_id)

        # Generate unique run_id for this streaming session
        run_id = str(uuid.uuid4())

        async def event_generator():
            # Capture initial message count to identify new messages
            initial_message_count = len(agency_instance.thread_manager.get_all_messages())

            active_run: ActiveRun | None = None

            async def _emit_oauth(payload: dict[str, Any]) -> AsyncGenerator[str]:
                event_type = payload.get("type")
                data = {
                    "state": payload.get("state"),
                    "server": payload.get("server"),
                }
                if event_type == "oauth_redirect":
                    data["auth_url"] = payload.get("auth_url")
                    name = "oauth_redirect"
                else:
                    name = "oauth_status"
                yield f"event: {name}\ndata: {json.dumps(data)}\n\n"

            queue_task: asyncio.Task | None = (
                asyncio.create_task(oauth_runtime.next_event()) if oauth_runtime is not None else None
            )

            if oauth_runtime:
                connect_task = asyncio.create_task(attach_persistent_mcp_servers(agency_instance))
                while True:
                    wait_set = {connect_task}
                    if queue_task:
                        wait_set.add(queue_task)
                    done, _ = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)

                    if queue_task and queue_task in done:
                        try:
                            payload = queue_task.result()
                            async for oauth_chunk in _emit_oauth(payload):
                                yield oauth_chunk
                        finally:
                            queue_task = asyncio.create_task(oauth_runtime.next_event())

                    if connect_task in done:
                        try:
                            await connect_task
                        except Exception as exc:
                            if queue_task:
                                queue_task.cancel()
                            yield "data: " + json.dumps({"error": str(exc)}) + "\n\n"
                            return
                        break
            else:
                await attach_persistent_mcp_servers(agency_instance)

            stream_events = None
            stream_task: asyncio.Task | None = None
            try:
                stream_events = agency_instance.get_response_stream(
                    message=request.message,
                    recipient_agent=request.recipient_agent,
                    context_override=request.user_context,
                    additional_instructions=request.additional_instructions,
                    file_ids=combined_file_ids,
                )

                active_run = ActiveRun(
                    stream=stream_events,
                    agency=agency_instance,
                    initial_message_count=initial_message_count,
                )
                await run_registry.register(run_id, active_run)

                # Now send run_id - client can safely call cancel endpoint
                yield f"event: meta\ndata: {json.dumps({'run_id': run_id})}\n\n"
                stream_task = asyncio.create_task(stream_events.__anext__())
                while stream_task:
                    wait_set = {stream_task}
                    if queue_task:
                        wait_set.add(queue_task)

                    done, _ = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)

                    if queue_task and queue_task in done:
                        try:
                            payload = queue_task.result()
                            async for oauth_chunk in _emit_oauth(payload):
                                yield oauth_chunk
                        finally:
                            queue_task = asyncio.create_task(oauth_runtime.next_event()) if oauth_runtime else None

                    if stream_task in done:
                        try:
                            event = stream_task.result()
                        except StopAsyncIteration:
                            break
                        except Exception as exc:
                            raise exc
                        if await http_request.is_disconnected():
                            logger.info(f"Client disconnected, cancelling run {run_id}")
                            stream_events.cancel(mode="immediate")
                            if active_run is not None:
                                active_run.cancelled = True
                                active_run.cancel_mode = "immediate"
                            break
                        try:
                            data = serialize(event)
                            yield "data: " + json.dumps({"data": data}) + "\n\n"
                        except Exception as e:
                            yield "data: " + json.dumps({"error": f"Failed to serialize event: {e}"}) + "\n\n"
                        stream_task = asyncio.create_task(stream_events.__anext__())
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
                    final_result = stream_events.final_result if stream_events else None
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
                            result["chat_name"] = await generate_chat_name(filtered_messages)
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
                    if queue_task and not queue_task.done():
                        queue_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await queue_task
                    if stream_task and not stream_task.done():
                        stream_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await stream_task
                    if stream_events:
                        with contextlib.suppress(Exception):
                            await stream_events.aclose()
                    await run_registry.finish(run_id)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
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
    oauth_config: FastAPIOAuthConfig | None = None,
):
    user_header = oauth_config.user_header if oauth_config else "X-User-Id"

    async def handler(
        request: request_model,
        token: str = Depends(verify_token),
        user_id: str | None = Header(default=None, alias=user_header),
    ):
        """Accepts AG-UI `RunAgentInput`, returns an AG-UI event stream."""

        encoder = EventEncoder()

        combined_file_ids = list(request.file_ids or []) if getattr(request, "file_ids", None) else []
        if getattr(request, "file_urls", None):
            try:
                file_ids_map = await upload_from_urls(request.file_urls, allowed_local_dirs=allowed_local_dirs)
                combined_file_ids = combined_file_ids + list(file_ids_map.values())
            except Exception as exc:
                error_message = f"Error downloading file from provided urls: {exc}"
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

        # Determine the message source and extract input message
        # Priority: chat_history (if has content) > messages (if has content)
        has_chat_history = request.chat_history is not None and len(request.chat_history) > 0
        has_messages = request.messages is not None and len(request.messages) > 0

        if has_chat_history:
            # Chat history is now a flat list
            def load_callback() -> list:
                return request.chat_history

            # Extract input message from last chat_history entry
            last_chat_msg = request.chat_history[-1]
            input_message = last_chat_msg.get("content", "")
            # Snapshot is empty since we're using chat_history format
            initial_snapshot: list = []

        elif has_messages:
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

            # Extract input message from last AG-UI message
            input_message = request.messages[-1].content
            # Store snapshot in dict format for AG-UI protocol
            initial_snapshot = [message.model_dump() for message in request.messages]

        else:
            # No messages available - will return error in event_generator
            def load_callback() -> list:
                return []

            input_message = None
            initial_snapshot = []

        oauth_runtime = None
        if oauth_config:
            oauth_runtime = FastAPIOAuthRuntime(oauth_config.registry, user_id, timeout=oauth_config.timeout)

        # Choose / build an agent – here we just create a demo agent each time.
        agency = agency_factory(load_threads_callback=load_callback)

        # Apply custom OpenAI client configuration if provided
        if request.client_config is not None:
            apply_openai_client_config(agency, request.client_config)

        oauth_runtime = _prepare_oauth_runtime(agency, oauth_runtime, user_id)

        async def event_generator() -> AsyncGenerator[str]:
            queue_task: asyncio.Task | None = (
                asyncio.create_task(oauth_runtime.next_event()) if oauth_runtime is not None else None
            )

            async def _emit_oauth(payload: dict[str, Any]) -> AsyncGenerator[str]:
                event_type = payload.get("type")
                data = {
                    "state": payload.get("state"),
                    "server": payload.get("server"),
                }
                if event_type == "oauth_redirect":
                    data["auth_url"] = payload.get("auth_url")
                    name = "oauth_redirect"
                else:
                    name = "oauth_status"
                yield f"event: {name}\ndata: {json.dumps(data)}\n\n"

            # Emit RUN_STARTED first.
            yield encoder.encode(
                RunStartedEvent(
                    type=EventType.RUN_STARTED,
                    thread_id=request.thread_id,
                    run_id=request.run_id,
                )
            )

            stream_events: Any | None = None
            stream_task: asyncio.Task | None = None
            try:
                # Handle error case: no messages available
                if input_message is None:
                    raise ValueError(
                        "No messages provided. Either 'messages' or 'chat_history' must contain at least one message."
                    )

                if oauth_runtime:
                    connect_task = asyncio.create_task(attach_persistent_mcp_servers(agency))
                    while True:
                        wait_set = {connect_task}
                        if queue_task:
                            wait_set.add(queue_task)
                        done, _ = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)

                        if queue_task and queue_task in done:
                            try:
                                payload = queue_task.result()
                                async for oauth_chunk in _emit_oauth(payload):
                                    yield oauth_chunk
                            finally:
                                queue_task = asyncio.create_task(oauth_runtime.next_event())

                        if connect_task in done:
                            try:
                                await connect_task
                            except Exception as exc:
                                if queue_task:
                                    queue_task.cancel()
                                yield encoder.encode(RunErrorEvent(type=EventType.RUN_ERROR, message=str(exc)))
                                return
                            break
                else:
                    await attach_persistent_mcp_servers(agency)

                # Create AguiAdapter instance with clean state for this request
                agui_adapter = AguiAdapter()

                # Use the pre-computed snapshot
                snapshot_messages = list(initial_snapshot)
                stream_events = agency.get_response_stream(
                    message=input_message,
                    context_override=request.user_context,
                    additional_instructions=request.additional_instructions,
                    file_ids=combined_file_ids or None,
                )
                stream_task = asyncio.create_task(stream_events.__anext__())
                while stream_task:
                    wait_set = {stream_task}
                    if queue_task:
                        wait_set.add(queue_task)

                    done, _ = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)

                    if queue_task and queue_task in done:
                        try:
                            payload = queue_task.result()
                            async for oauth_chunk in _emit_oauth(payload):
                                yield oauth_chunk
                        finally:
                            queue_task = asyncio.create_task(oauth_runtime.next_event()) if oauth_runtime else None

                    if stream_task in done:
                        try:
                            stream_event = stream_task.result()
                        except StopAsyncIteration:
                            break
                        agui_event = agui_adapter.openai_to_agui_events(
                            stream_event,
                            run_id=request.run_id,
                        )
                        if agui_event:
                            agui_events: list[BaseEvent] = agui_event if isinstance(agui_event, list) else [agui_event]
                            for agui_event_item in agui_events:
                                if isinstance(agui_event_item, MessagesSnapshotEvent):
                                    snapshot_messages.append(agui_event_item.messages[0].model_dump())
                                    yield encoder.encode(
                                        MessagesSnapshotEvent(
                                            type=EventType.MESSAGES_SNAPSHOT, messages=snapshot_messages
                                        )
                                    )
                                else:
                                    yield encoder.encode(agui_event_item)
                        stream_task = asyncio.create_task(stream_events.__anext__())

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
                if queue_task and not queue_task.done():
                    queue_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await queue_task
                if stream_task and not stream_task.done():
                    stream_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await stream_task
                if stream_events:
                    with contextlib.suppress(Exception):
                        await stream_events.aclose()

        return StreamingResponse(event_generator(), media_type=encoder.get_content_type())

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


def make_metadata_endpoint(agency_metadata: dict, verify_token):
    async def handler(token: str = Depends(verify_token)):
        metadata_with_version = dict(agency_metadata)
        agency_swarm_version = _get_agency_swarm_version()
        if agency_swarm_version is not None:
            metadata_with_version["agency_swarm_version"] = agency_swarm_version
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


async def generate_chat_name(new_messages: list[TResponseInputItem]):
    client = get_default_openai_client() or AsyncOpenAI()

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

"""Streaming SSE endpoint factory."""

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator, Callable, Sequence
from pathlib import Path

from agents import TResponseInputItem
from agents.exceptions import OutputGuardrailTripwireTriggered
from fastapi import Depends, Request
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI

from agency_swarm import Agency
from agency_swarm.integrations.fastapi_utils import endpoint_handlers
from agency_swarm.integrations.fastapi_utils.client_overrides import _resolve_stream_client_config
from agency_swarm.integrations.fastapi_utils.message_builders import (
    _build_chat_name_messages,
    _build_message_with_file_urls_context,
    _normalize_new_messages_for_client,
)
from agency_swarm.integrations.fastapi_utils.oauth_helpers import (
    _clear_oauth_request_context,
    _encode_oauth,
    _ensure_request_oauth_config,
    _no_oauth_user_id,
    _requires_oauth_agent_state_restore,
    _resolve_oauth_user_id,
    _with_oauth_user_context,
)
from agency_swarm.integrations.fastapi_utils.oauth_support import FastAPIOAuthConfig, FastAPIOAuthRuntime
from agency_swarm.integrations.fastapi_utils.override_policy import RequestOverridePolicy
from agency_swarm.integrations.fastapi_utils.override_session import _RequestOverrideSession
from agency_swarm.integrations.fastapi_utils.request_lifecycle import _wait_for_cleanup
from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest
from agency_swarm.integrations.fastapi_utils.run_registry import ActiveRun, ActiveRunRegistry
from agency_swarm.integrations.fastapi_utils.stream_lifecycle import _StreamLifecycle
from agency_swarm.integrations.fastapi_utils.stream_response import _OwnedStreamingResponse
from agency_swarm.messages import MessageFilter
from agency_swarm.utils.serialization import serialize
from agency_swarm.utils.usage_tracking import (
    calculate_usage_with_cost,
    extract_usage_from_run_result,
)

# Keep the pre-split logger name so log records are unchanged.
logger = logging.getLogger("agency_swarm.integrations.fastapi_utils.endpoint_handlers")


# Streaming SSE endpoint
def make_stream_endpoint(
    request_model,
    agency_factory: Callable[..., Agency],
    verify_token,
    run_registry: ActiveRunRegistry,
    allowed_local_dirs: Sequence[str | Path] | None = None,
    oauth_config: FastAPIOAuthConfig | None = None,
):
    user_id_dependency = oauth_config.user_id_dependency if oauth_config else _no_oauth_user_id

    async def handler(
        http_request: Request,
        request: request_model,
        token: str = Depends(verify_token),
        user_id: object = Depends(user_id_dependency),
    ):
        user_id = _resolve_oauth_user_id(user_id, oauth_config)
        if request.chat_history is not None:
            # Chat history is now a flat list
            def load_callback() -> list:
                return request.chat_history
        else:

            def load_callback() -> list:
                return []

        oauth_runtime = None
        if oauth_config:
            oauth_runtime = FastAPIOAuthRuntime(
                oauth_config.registry,
                user_id,
                timeout=oauth_config.timeout,
                enable_hosted_mcp_oauth=oauth_config.enable_hosted_mcp_oauth,
            )

        agency_instance = agency_factory(load_threads_callback=load_callback)
        _ensure_request_oauth_config(agency_instance, oauth_config)
        client_config = _resolve_stream_client_config(http_request, request.client_config)
        request_user_context = _with_oauth_user_context(request.user_context, user_id)
        override_policy = RequestOverridePolicy(client_config)
        override_session = _RequestOverrideSession(
            agency=agency_instance,
            policy=override_policy,
            restore_oauth_state=_requires_oauth_agent_state_restore(agency_instance, oauth_runtime),
        )
        request_upload_client: AsyncOpenAI | None = None

        combined_file_ids = request.file_ids
        file_ids_map = None
        message_input: str | list[TResponseInputItem] = request.message

        async def cleanup_setup_context() -> None:
            try:
                await override_session.cleanup()
            finally:
                _clear_oauth_request_context()

        try:
            await override_session.acquire()
            oauth_runtime = endpoint_handlers._prepare_oauth_runtime(agency_instance, oauth_runtime, user_id)

            request_upload_client = endpoint_handlers._build_file_upload_client(
                agency_instance,
                client_config,
                recipient_agent=request.recipient_agent,
            )
            if request.file_urls is not None:
                try:
                    file_ids_map = await endpoint_handlers.upload_from_urls(
                        request.file_urls,
                        allowed_local_dirs=allowed_local_dirs,
                        openai_client=request_upload_client,
                    )
                    combined_file_ids = (combined_file_ids or []) + list(file_ids_map.values())
                    message_input = _build_message_with_file_urls_context(
                        request.message,
                        request.file_urls,
                        file_ids_map,
                    )
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
        except BaseException:
            await cleanup_setup_context()
            raise

        run_id = str(uuid.uuid4())

        async def cleanup_stream_context() -> None:
            try:
                await override_session.cleanup()
            finally:
                _clear_oauth_request_context()

        async def event_generator() -> AsyncGenerator[str]:
            initial_message_count = len(agency_instance.thread_manager.get_all_messages())
            active_run: ActiveRun | None = None
            lifecycle: _StreamLifecycle | None = None
            disconnected = False
            aborted = True
            final_frames: list[str] = []
            try:
                stream = agency_instance.get_response_stream(
                    message=message_input,
                    recipient_agent=request.recipient_agent,
                    context_override=request_user_context,
                    additional_instructions=request.additional_instructions,
                    file_ids=combined_file_ids,
                )
                active_run = ActiveRun(stream, agency_instance, initial_message_count)
                lifecycle = _StreamLifecycle(agency_instance, stream, oauth_runtime, _encode_oauth, active_run)
                await run_registry.register(run_id, active_run)
                yield f"event: meta\ndata: {json.dumps({'run_id': run_id})}\n\n"
                async for event in lifecycle.events():
                    if await http_request.is_disconnected():
                        disconnected = True
                        active_run.cancelled = True
                        active_run.cancel_mode = "immediate"
                        break
                    yield event if isinstance(event, str) else _encode_stream_event(event)
                aborted = False
            except Exception as exc:
                yield _encode_stream_error(exc)
                aborted = False
            finally:
                try:
                    if lifecycle is not None:
                        await lifecycle.close()
                    if not aborted and not disconnected:
                        final_frames = [
                            frame
                            async for frame in _final_frames(
                                agency_instance,
                                active_run,
                                initial_message_count,
                                run_id,
                                request,
                                file_ids_map,
                                request_upload_client,
                            )
                        ]
                finally:
                    try:
                        await cleanup_stream_context()
                    finally:
                        await _wait_for_cleanup(asyncio.create_task(run_registry.finish(run_id)))
            # Protocol output belongs to normal iteration. aclose()/ASGI
            # cancellation must run cleanup without yielding from a finally.
            for frame in final_frames:
                yield frame

        return _OwnedStreamingResponse(
            event_generator(),
            cleanup_stream_context,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    return handler


def _encode_stream_event(event: object) -> str:
    try:
        return "data: " + json.dumps({"data": serialize(event)}) + "\n\n"
    except Exception as exc:
        return "data: " + json.dumps({"error": f"Failed to serialize event: {exc}"}) + "\n\n"


def _encode_stream_error(exc: Exception) -> str:
    if isinstance(exc, OutputGuardrailTripwireTriggered):
        error = "Guardrail OutputGuardrail triggered tripwire: " + str(exc.guardrail_result.output.output_info)
    else:
        error = str(exc)
    return "data: " + json.dumps({"error": error}) + "\n\n"


def _new_messages(agency: Agency, initial_count: int) -> list[TResponseInputItem]:
    messages = agency.thread_manager.get_all_messages()[initial_count:]
    messages = MessageFilter.remove_duplicates(messages)
    messages = MessageFilter.filter_messages(messages)
    messages = MessageFilter.remove_orphaned_messages(messages)
    return _normalize_new_messages_for_client(messages)


async def _final_frames(
    agency: Agency,
    active_run: ActiveRun | None,
    initial_count: int,
    run_id: str,
    request: BaseRequest,
    file_ids_map: dict[str, str] | None,
    upload_client: AsyncOpenAI | None,
) -> AsyncGenerator[str]:
    try:
        messages = _new_messages(agency, initial_count)
        result: dict[str, object] = {"new_messages": messages, "run_id": run_id}
        if active_run is not None and active_run.cancelled:
            result["cancelled"] = True
        if request.file_urls is not None and file_ids_map is not None:
            result["file_ids_map"] = file_ids_map
        final_result = active_run.stream.final_result if active_run else None
        usage = extract_usage_from_run_result(final_result)
        if usage:
            result["usage"] = calculate_usage_with_cost(usage, run_result=final_result).to_dict()
        if request.generate_chat_name:
            try:
                result["chat_name"] = await endpoint_handlers.generate_chat_name(
                    _build_chat_name_messages(messages),
                    openai_client=upload_client,
                )
            except Exception as exc:
                logger.error("Error generating chat name: %s", exc)
        yield "event: messages\ndata: " + json.dumps(result) + "\n\n"
    except Exception as exc:
        logger.error("Error building final response: %s", exc)
        yield "data: " + json.dumps({"error": f"Error building response: {exc}"}) + "\n\n"
    yield "event: end\ndata: [DONE]\n\n"

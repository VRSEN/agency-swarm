"""Streaming SSE endpoint factory."""

import asyncio
import contextlib
import json
import logging
import uuid
from collections.abc import AsyncGenerator, Callable, Sequence
from pathlib import Path
from typing import Any

from agents import TResponseInputItem
from agents.exceptions import OutputGuardrailTripwireTriggered
from fastapi import Depends, Request
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from starlette.background import BackgroundTask

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
    _ensure_request_oauth_config,
    _no_oauth_user_id,
    _requires_oauth_agent_state_restore,
    _resolve_oauth_user_id,
    _sse_keepalive_comment,
    _update_oauth_pending,
    _with_oauth_user_context,
)
from agency_swarm.integrations.fastapi_utils.oauth_support import FastAPIOAuthConfig, FastAPIOAuthRuntime
from agency_swarm.integrations.fastapi_utils.override_policy import RequestOverridePolicy
from agency_swarm.integrations.fastapi_utils.override_session import _RequestOverrideSession
from agency_swarm.integrations.fastapi_utils.run_registry import ActiveRun, ActiveRunRegistry
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
            await override_session.cleanup()
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
                _clear_oauth_request_context()

        async def event_generator():
            # Capture initial message count to identify new messages
            initial_message_count = len(agency_instance.thread_manager.get_all_messages())

            stream = None
            stream_task: asyncio.Task | None = None
            connect_task: asyncio.Task | None = None
            cancel_task: asyncio.Task | None = None
            active_run: ActiveRun | None = None
            oauth_pending: set[str] = set()
            queue_task: asyncio.Task | None = (
                asyncio.create_task(oauth_runtime.next_event()) if oauth_runtime is not None else None
            )
            keepalive_task: asyncio.Task | None = None

            async def _emit_oauth(payload: dict[str, Any]) -> AsyncGenerator[str]:
                event_type = payload.get("type")
                data = {
                    "state": payload.get("state"),
                    "server": payload.get("server"),
                }
                if event_type == "oauth_redirect":
                    data["auth_url"] = payload.get("auth_url")
                    name = "oauth_redirect"
                elif event_type == "oauth_status":
                    data["status"] = payload.get("status")
                    name = "oauth_status"
                else:
                    return
                yield f"event: {name}\ndata: {json.dumps(data)}\n\n"

            try:
                stream = agency_instance.get_response_stream(
                    message=message_input,
                    recipient_agent=request.recipient_agent,
                    context_override=request_user_context,
                    additional_instructions=request.additional_instructions,
                    file_ids=combined_file_ids,
                )

                active_run = ActiveRun(
                    stream=stream,
                    agency=agency_instance,
                    initial_message_count=initial_message_count,
                )
                await run_registry.register(run_id, active_run)
                cancel_task = asyncio.create_task(active_run.cancel_event.wait())

                # Now send run_id - client can safely call cancel endpoint
                yield f"event: meta\ndata: {json.dumps({'run_id': run_id})}\n\n"

                if oauth_runtime:
                    connect_task = asyncio.create_task(endpoint_handlers.attach_persistent_mcp_servers(agency_instance))
                    while True:
                        wait_set = {connect_task}
                        if queue_task:
                            wait_set.add(queue_task)
                        if keepalive_task:
                            wait_set.add(keepalive_task)
                        if cancel_task:
                            wait_set.add(cancel_task)
                        done, _ = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)

                        if cancel_task and cancel_task in done:
                            connect_task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await connect_task
                            break

                        if queue_task and queue_task in done:
                            try:
                                payload = queue_task.result()
                                _update_oauth_pending(oauth_pending, payload)
                                async for oauth_chunk in _emit_oauth(payload):
                                    yield oauth_chunk
                                if oauth_pending and keepalive_task is None:
                                    keepalive_task = asyncio.create_task(
                                        asyncio.sleep(endpoint_handlers.OAUTH_KEEPALIVE_SECONDS)
                                    )
                                if not oauth_pending and keepalive_task is not None:
                                    keepalive_task.cancel()
                                    with contextlib.suppress(asyncio.CancelledError):
                                        await keepalive_task
                                    keepalive_task = None
                            finally:
                                queue_task = asyncio.create_task(oauth_runtime.next_event())

                        if keepalive_task and keepalive_task in done:
                            if oauth_pending:
                                yield _sse_keepalive_comment()
                                keepalive_task = asyncio.create_task(
                                    asyncio.sleep(endpoint_handlers.OAUTH_KEEPALIVE_SECONDS)
                                )
                            else:
                                keepalive_task = None

                        if connect_task in done:
                            await connect_task
                            if oauth_pending:
                                yield _sse_keepalive_comment()
                            break
                else:
                    await endpoint_handlers.attach_persistent_mcp_servers(agency_instance)

                stream_iter = stream.__aiter__()
                if active_run.cancelled:
                    stream_task = None
                else:
                    stream_task = asyncio.create_task(stream_iter.__anext__())
                while stream_task:
                    wait_set = {stream_task}
                    if queue_task:
                        wait_set.add(queue_task)
                    if keepalive_task:
                        wait_set.add(keepalive_task)
                    if cancel_task:
                        wait_set.add(cancel_task)

                    done, _ = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)

                    if cancel_task and cancel_task in done:
                        stream_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await stream_task
                        break

                    if queue_task and queue_task in done:
                        try:
                            payload = queue_task.result()
                            _update_oauth_pending(oauth_pending, payload)
                            async for oauth_chunk in _emit_oauth(payload):
                                yield oauth_chunk
                            if oauth_pending and keepalive_task is None:
                                keepalive_task = asyncio.create_task(
                                    asyncio.sleep(endpoint_handlers.OAUTH_KEEPALIVE_SECONDS)
                                )
                            if not oauth_pending and keepalive_task is not None:
                                keepalive_task.cancel()
                                with contextlib.suppress(asyncio.CancelledError):
                                    await keepalive_task
                                keepalive_task = None
                        finally:
                            queue_task = asyncio.create_task(oauth_runtime.next_event()) if oauth_runtime else None

                    if keepalive_task and keepalive_task in done:
                        if oauth_pending:
                            yield _sse_keepalive_comment()
                            keepalive_task = asyncio.create_task(
                                asyncio.sleep(endpoint_handlers.OAUTH_KEEPALIVE_SECONDS)
                            )
                        else:
                            keepalive_task = None

                    if stream_task in done:
                        try:
                            event = stream_task.result()
                        except StopAsyncIteration:
                            break
                        except Exception as exc:
                            raise exc

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

                        stream_task = asyncio.create_task(stream_iter.__anext__())

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
                            result["chat_name"] = await endpoint_handlers.generate_chat_name(
                                _build_chat_name_messages(filtered_messages),
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
                    if keepalive_task and not keepalive_task.done():
                        keepalive_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await keepalive_task
                    if queue_task and not queue_task.done():
                        queue_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await queue_task
                    if stream_task and not stream_task.done():
                        stream_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await stream_task
                    if cancel_task and not cancel_task.done():
                        cancel_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await cancel_task
                    if connect_task and not connect_task.done():
                        connect_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await connect_task
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

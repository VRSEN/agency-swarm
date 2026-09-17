"""AG-UI chat endpoint factory."""

import asyncio
import contextlib
import json
import logging
import time
import traceback
from collections.abc import AsyncGenerator, Callable, Sequence
from pathlib import Path
from typing import Any

from ag_ui.core import (
    BaseEvent,
    EventType,
    MessagesSnapshotEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
)
from ag_ui.encoder import EventEncoder
from agents import TResponseInputItem
from fastapi import Depends
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from starlette.background import BackgroundTask

from agency_swarm import Agency
from agency_swarm.integrations.fastapi_utils import endpoint_handlers
from agency_swarm.integrations.fastapi_utils.message_builders import (
    _build_agui_message_input,
    _build_agui_snapshot_messages,
    _build_message_with_file_urls_context,
    _normalize_agui_history_messages,
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

# Keep the pre-split logger name so log records are unchanged.
logger = logging.getLogger("agency_swarm.integrations.fastapi_utils.endpoint_handlers")


def make_agui_chat_endpoint(
    request_model,
    agency_factory: Callable[..., Agency],
    verify_token,
    allowed_local_dirs: Sequence[str | Path] | None = None,
    oauth_config: FastAPIOAuthConfig | None = None,
):
    user_id_dependency = oauth_config.user_id_dependency if oauth_config else _no_oauth_user_id

    async def handler(
        request: request_model,
        token: str = Depends(verify_token),
        user_id: object = Depends(user_id_dependency),
    ):
        """Accepts AG-UI `RunAgentInput`, returns an AG-UI event stream."""
        user_id = _resolve_oauth_user_id(user_id, oauth_config)

        encoder = EventEncoder()

        combined_file_ids = list(request.file_ids or []) if getattr(request, "file_ids", None) else []
        message_input: str | list[TResponseInputItem] | None
        try:
            message_input = _build_agui_message_input(request.messages)
        except Exception as exc:
            run_started = RunStartedEvent(
                type=EventType.RUN_STARTED,
                thread_id=request.thread_id,
                run_id=request.run_id,
            )
            run_error = RunErrorEvent(type=EventType.RUN_ERROR, message=f"Error converting AG-UI message: {exc}")
            run_finished = RunFinishedEvent(
                type=EventType.RUN_FINISHED,
                thread_id=request.thread_id,
                run_id=request.run_id,
            )
            return StreamingResponse(
                (encoder.encode(event) for event in (run_started, run_error, run_finished)),
                media_type=encoder.get_content_type(),
            )

        # Determine the message source and extract input message.
        # `chat_history` replays prior context; `messages` carries the current input.
        # When only `chat_history` has content, its last entry is the current input.
        has_chat_history = request.chat_history is not None and len(request.chat_history) > 0
        has_messages = request.messages is not None and len(request.messages) > 0

        if has_chat_history and not has_messages:
            # Chat history is a flat list; the last entry is the current input.
            def load_callback() -> list:
                return request.chat_history[:-1]

            message_input = request.chat_history[-1].get("content", "")

        elif has_chat_history:
            # Chat history is now a flat list of prior turns.
            def load_callback() -> list:
                return request.chat_history

        elif has_messages:
            # Pull the default agent from the agency
            agency = agency_factory()
            _ensure_request_oauth_config(agency, oauth_config)
            default_agent = agency.entry_points[0]

            # Convert AG-UI messages to flat chat history with metadata
            def load_callback() -> list:
                agui_messages = _normalize_agui_history_messages(
                    endpoint_handlers.AguiAdapter.agui_messages_to_chat_history(request.messages)
                )
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

            if not getattr(request, "file_urls", None) and not combined_file_ids:
                # Attachment-only requests keep the empty converted input; anything
                # else without messages or chat history is a client error.
                message_input = None

        oauth_runtime = None
        if oauth_config:
            oauth_runtime = FastAPIOAuthRuntime(
                oauth_config.registry,
                user_id,
                timeout=oauth_config.timeout,
                enable_hosted_mcp_oauth=oauth_config.enable_hosted_mcp_oauth,
            )

        # Choose / build an agent – here we just create a demo agent each time.
        agency = agency_factory(load_threads_callback=load_callback)
        _ensure_request_oauth_config(agency, oauth_config)
        request_user_context = _with_oauth_user_context(request.user_context, user_id)
        override_policy = RequestOverridePolicy(request.client_config)
        override_session = _RequestOverrideSession(
            agency=agency,
            policy=override_policy,
            restore_oauth_state=_requires_oauth_agent_state_restore(agency, oauth_runtime),
        )
        request_upload_client: AsyncOpenAI | None = None

        async def cleanup_setup_context() -> None:
            await override_session.cleanup()
            _clear_oauth_request_context()

        try:
            await override_session.acquire()
            oauth_runtime = endpoint_handlers._prepare_oauth_runtime(agency, oauth_runtime, user_id)

            request_upload_client = endpoint_handlers._build_file_upload_client(
                agency, request.client_config, recipient_agent=None
            )
            if getattr(request, "file_urls", None):
                try:
                    file_ids_map = await endpoint_handlers.upload_from_urls(
                        request.file_urls,
                        allowed_local_dirs=allowed_local_dirs,
                        openai_client=request_upload_client,
                    )
                    combined_file_ids = combined_file_ids + list(file_ids_map.values())
                    if message_input is not None:
                        message_input = _build_message_with_file_urls_context(
                            message_input,
                            request.file_urls,
                            file_ids_map,
                        )
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
                _clear_oauth_request_context()

        async def event_generator() -> AsyncGenerator[str]:
            # Emit RUN_STARTED first.
            yield encoder.encode(
                RunStartedEvent(
                    type=EventType.RUN_STARTED,
                    thread_id=request.thread_id,
                    run_id=request.run_id,
                )
            )

            queue_task: asyncio.Task | None = (
                asyncio.create_task(oauth_runtime.next_event()) if oauth_runtime is not None else None
            )
            keepalive_task: asyncio.Task | None = None
            connect_task: asyncio.Task | None = None
            stream_task: asyncio.Task | None = None
            oauth_pending: set[str] = set()

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
                # Handle error case: no messages available
                if message_input is None:
                    raise ValueError(
                        "No messages provided. Either 'messages' or 'chat_history' must contain at least one message."
                    )

                # Create AguiAdapter instance with clean state for this request
                agui_adapter = endpoint_handlers.AguiAdapter()

                snapshot_messages = _build_agui_snapshot_messages(list(request.messages or []), message_input)
                stream_events = agency.get_response_stream(
                    message=message_input,
                    context_override=request_user_context,
                    additional_instructions=request.additional_instructions,
                    file_ids=combined_file_ids or None,
                )

                if oauth_runtime:
                    connect_task = asyncio.create_task(endpoint_handlers.attach_persistent_mcp_servers(agency))
                    while True:
                        wait_set: set[asyncio.Task[Any]] = {connect_task}
                        if queue_task:
                            wait_set.add(queue_task)
                        if keepalive_task:
                            wait_set.add(keepalive_task)
                        done, _ = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)

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
                    await endpoint_handlers.attach_persistent_mcp_servers(agency)

                stream_iter = stream_events.__aiter__()
                stream_task = asyncio.create_task(stream_iter.__anext__())
                while stream_task:
                    wait_set = {stream_task}
                    if queue_task:
                        wait_set.add(queue_task)
                    if keepalive_task:
                        wait_set.add(keepalive_task)

                    done, _ = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)

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
                            stream_event = stream_task.result()
                        except StopAsyncIteration:
                            break

                        agui_event = agui_adapter.openai_to_agui_events(stream_event, run_id=request.run_id)
                        if agui_event:
                            agui_events: list[BaseEvent] = agui_event if isinstance(agui_event, list) else [agui_event]
                            for agui_evt in agui_events:
                                if isinstance(agui_evt, MessagesSnapshotEvent):
                                    snapshot_messages.append(agui_evt.messages[0])
                                    yield encoder.encode(
                                        MessagesSnapshotEvent(
                                            type=EventType.MESSAGES_SNAPSHOT, messages=snapshot_messages
                                        )
                                    )
                                else:
                                    yield encoder.encode(agui_evt)

                        stream_task = asyncio.create_task(stream_iter.__anext__())

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
                if keepalive_task and not keepalive_task.done():
                    keepalive_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await keepalive_task
                if queue_task and not queue_task.done():
                    queue_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await queue_task
                if connect_task and not connect_task.done():
                    connect_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await connect_task
                if stream_task and not stream_task.done():
                    stream_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await stream_task
                await cleanup_stream_context()

        return StreamingResponse(
            event_generator(),
            media_type=encoder.get_content_type(),
            background=BackgroundTask(cleanup_stream_context),
        )

    return handler

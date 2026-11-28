"""AG-UI chat endpoint factory."""

import logging
import time
import traceback
from collections.abc import AsyncGenerator, Callable, Sequence
from pathlib import Path

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
from agency_swarm.integrations.fastapi_utils.stream_lifecycle import _StreamLifecycle
from agency_swarm.integrations.fastapi_utils.stream_response import _OwnedStreamingResponse

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
            try:
                await override_session.cleanup()
            finally:
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
        except BaseException:
            await cleanup_setup_context()
            raise

        async def cleanup_stream_context() -> None:
            try:
                await override_session.cleanup()
            finally:
                _clear_oauth_request_context()

        async def event_generator() -> AsyncGenerator[str]:
            lifecycle: _StreamLifecycle | None = None
            try:
                yield encoder.encode(
                    RunStartedEvent(type=EventType.RUN_STARTED, thread_id=request.thread_id, run_id=request.run_id)
                )
                if message_input is None:
                    raise ValueError(
                        "No messages provided. Either 'messages' or 'chat_history' must contain at least one message."
                    )
                adapter = endpoint_handlers.AguiAdapter()
                snapshot_messages = _build_agui_snapshot_messages(list(request.messages or []), message_input)
                stream = agency.get_response_stream(
                    message=message_input,
                    context_override=request_user_context,
                    additional_instructions=request.additional_instructions,
                    file_ids=combined_file_ids or None,
                )
                lifecycle = _StreamLifecycle(agency, stream, oauth_runtime, _encode_oauth)
                async for event in lifecycle.events():
                    if isinstance(event, str):
                        yield event
                        continue
                    converted = adapter.openai_to_agui_events(event, run_id=request.run_id)
                    events: list[BaseEvent] = (
                        converted if isinstance(converted, list) else [converted] if converted else []
                    )
                    for agui_event in events:
                        if isinstance(agui_event, MessagesSnapshotEvent):
                            snapshot_messages.extend(agui_event.messages)
                            agui_event = MessagesSnapshotEvent(
                                type=EventType.MESSAGES_SNAPSHOT, messages=snapshot_messages
                            )
                        yield encoder.encode(agui_event)
                yield encoder.encode(
                    RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id=request.thread_id, run_id=request.run_id)
                )
            except Exception as exc:
                tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                yield encoder.encode(RunErrorEvent(type=EventType.RUN_ERROR, message=f"{exc}\n\nTraceback:\n{tb_str}"))
            finally:
                try:
                    if lifecycle is not None:
                        await lifecycle.close()
                finally:
                    await cleanup_stream_context()

        return _OwnedStreamingResponse(
            event_generator(),
            cleanup_stream_context,
            media_type=encoder.get_content_type(),
        )

    return handler

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from typing import TYPE_CHECKING, Any, assert_never, cast

from agents.realtime import RealtimeRunner, RealtimeSession
from agents.realtime.config import (
    RealtimeInputAudioNoiseReductionConfig,
    RealtimeSessionModelSettings,
    RealtimeTurnDetectionConfig,
)
from agents.realtime.events import (
    RealtimeAgentEndEvent,
    RealtimeAgentStartEvent,
    RealtimeAudio,
    RealtimeAudioEnd,
    RealtimeAudioInterrupted,
    RealtimeError,
    RealtimeGuardrailTripped,
    RealtimeHandoffEvent,
    RealtimeHistoryAdded,
    RealtimeHistoryUpdated,
    RealtimeInputAudioTimeoutTriggered,
    RealtimeRawModelEvent,
    RealtimeSessionEvent,
    RealtimeToolEnd,
    RealtimeToolStart,
)
from agents.realtime.model_inputs import (
    RealtimeModelRawClientMessage,
    RealtimeModelSendRawMessage,
    RealtimeModelSendSessionUpdate,
)
from starlette.websockets import WebSocket as StarletteWebSocket, WebSocketDisconnect

from agency_swarm.agency.core import Agency
from agency_swarm.agent.core import Agent
from agency_swarm.context import MasterContext
from agency_swarm.realtime.agency import RealtimeAgency
from agency_swarm.utils.thread import ThreadManager

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

__all__ = ["run_realtime", "RealtimeSessionFactory", "build_model_settings"]


def _model_dump(item: Any) -> Any:
    """Convert SDK events to JSON-serializable data."""
    dump = getattr(item, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json")
        except TypeError:
            return dump()
    if isinstance(item, str | int | float | bool) or item is None:
        return item
    if isinstance(item, dict):
        return item
    return str(item)


def _serialize_event(event: RealtimeSessionEvent) -> dict[str, Any] | None:
    """Translate realtime session events to JSON payloads for websocket clients."""
    if isinstance(event, RealtimeAudio):
        audio_data = base64.b64encode(event.audio.data).decode("utf-8")
        return {
            "type": "audio",
            "audio": audio_data,
            "item_id": event.item_id,
            "content_index": event.content_index,
            "response_id": event.audio.response_id,
        }
    if isinstance(event, RealtimeAudioEnd):
        return {
            "type": "audio_end",
            "item_id": event.item_id,
            "content_index": event.content_index,
        }
    if isinstance(event, RealtimeAudioInterrupted):
        return {
            "type": "audio_interrupted",
            "item_id": event.item_id,
            "content_index": event.content_index,
        }
    if isinstance(event, RealtimeAgentStartEvent):
        return {"type": "agent_start", "agent": event.agent.name}
    if isinstance(event, RealtimeAgentEndEvent):
        return {"type": "agent_end", "agent": event.agent.name}
    if isinstance(event, RealtimeHandoffEvent):
        return {"type": "handoff", "from": event.from_agent.name, "to": event.to_agent.name}
    if isinstance(event, RealtimeToolStart):
        return {
            "type": "tool_start",
            "agent": event.agent.name,
            "tool": getattr(event.tool, "name", str(event.tool)),
        }
    if isinstance(event, RealtimeToolEnd):
        return {
            "type": "tool_end",
            "agent": event.agent.name,
            "tool": getattr(event.tool, "name", str(event.tool)),
            "output": str(event.output),
        }
    if isinstance(event, RealtimeHistoryUpdated):
        return {
            "type": "history_updated",
            "history": [_model_dump(item) for item in event.history],
        }
    if isinstance(event, RealtimeHistoryAdded):
        return {
            "type": "history_added",
            "item": _model_dump(event.item),
        }
    if isinstance(event, RealtimeGuardrailTripped):
        return {
            "type": "guardrail_tripped",
            "guardrails": [result.guardrail.get_name() for result in event.guardrail_results],
            "message": event.message,
        }
    if isinstance(event, RealtimeError):
        return {"type": "error", "error": str(event.error)}
    if isinstance(event, RealtimeRawModelEvent):
        raw_type = getattr(event.data, "type", "unknown")
        payload = getattr(event.data, "model_dump", None)
        data = payload(mode="json") if callable(payload) else str(event.data)
        return {"type": "raw_model_event", "raw_type": raw_type, "data": data}
    if isinstance(event, RealtimeInputAudioTimeoutTriggered):
        return {"type": "input_audio_timeout_triggered"}
    assert_never(event)


async def _forward_session_events(
    session: RealtimeSession,
    send: Callable[[str], Awaitable[Any]],
    *,
    initial_voice: str | None = None,
) -> None:
    current_voice = initial_voice
    async for event in session:
        if isinstance(event, RealtimeAgentStartEvent):
            desired_voice = getattr(event.agent, "voice", None)
            if desired_voice and desired_voice != current_voice:
                await session.model.send_event(
                    RealtimeModelSendSessionUpdate(session_settings={"voice": desired_voice})
                )
                logger.info("Updated realtime voice to %s for agent %s", desired_voice, event.agent.name)
                current_voice = desired_voice
        payload = _serialize_event(event)
        if payload is not None:
            await send(json.dumps(payload))


async def _handle_client_payload(session: RealtimeSession, payload: str) -> None:
    try:
        message = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("Ignoring non-JSON realtime payload: %s", payload[:80])
        return

    msg_type = message.get("type")
    if not isinstance(msg_type, str):
        logger.warning("Realtime payload missing 'type': %s", message)
        return

    if msg_type == "input_audio_buffer":
        audio = message.get("audio")
        if isinstance(audio, str):
            try:
                audio_bytes = base64.b64decode(audio)
            except (binascii.Error, ValueError):
                logger.warning("Failed to decode realtime audio payload.")
                return
            await session.send_audio(audio_bytes, commit=bool(message.get("commit", False)))
        else:
            logger.debug("Realtime audio payload missing 'audio' data.")
        return

    if msg_type == "interrupt":
        await session.interrupt()
        return

    other = {k: v for k, v in message.items() if k != "type"}
    raw_message: dict[str, Any] = {"type": msg_type}
    if other:
        raw_message["other_data"] = other
    client_message = cast(RealtimeModelRawClientMessage, raw_message)
    await session.model.send_event(RealtimeModelSendRawMessage(message=client_message))


def build_model_settings(
    *,
    model: str,
    voice: str | None,
    input_audio_format: str | None,
    output_audio_format: str | None,
    turn_detection: dict[str, Any] | None,
    input_audio_noise_reduction: dict[str, Any] | None,
) -> RealtimeSessionModelSettings:
    settings: RealtimeSessionModelSettings = {"model_name": model}
    if voice:
        settings["voice"] = voice
    if input_audio_format:
        settings["input_audio_format"] = input_audio_format
    if output_audio_format:
        settings["output_audio_format"] = output_audio_format
    if turn_detection:
        settings["turn_detection"] = cast(RealtimeTurnDetectionConfig, turn_detection)
    if input_audio_noise_reduction:
        settings["input_audio_noise_reduction"] = cast(
            RealtimeInputAudioNoiseReductionConfig, input_audio_noise_reduction
        )
    return settings


async def _forward_events_to_twilio(
    session: RealtimeSession,
    websocket: StarletteWebSocket,
    get_stream_sid: Callable[[], str | None],
    *,
    initial_voice: str | None = None,
) -> None:
    current_voice = initial_voice
    async for event in session:
        stream_sid = get_stream_sid()
        if stream_sid is None:
            continue

        if isinstance(event, RealtimeAgentStartEvent):
            desired_voice = getattr(event.agent, "voice", None)
            if desired_voice and desired_voice != current_voice:
                await session.model.send_event(
                    RealtimeModelSendSessionUpdate(session_settings={"voice": desired_voice})
                )
                logger.info("Updated realtime voice to %s for Twilio stream", desired_voice)
                current_voice = desired_voice
            continue

        if isinstance(event, RealtimeAudio):
            payload = base64.b64encode(event.audio.data).decode("utf-8")
            await websocket.send_text(
                json.dumps({"event": "media", "streamSid": stream_sid, "media": {"payload": payload}})
            )
        elif isinstance(event, RealtimeAudioInterrupted):
            await websocket.send_text(json.dumps({"event": "clear", "streamSid": stream_sid}))


class RealtimeSessionFactory:
    def __init__(self, realtime_agency: RealtimeAgency, base_model_settings: Mapping[str, Any]):
        self._agency = realtime_agency
        self._base_model_settings = dict(base_model_settings)

    @property
    def default_voice(self) -> str | None:
        voice_value = self._base_model_settings.get("voice")
        return cast(str | None, voice_value)

    async def create_session(self, overrides: dict[str, Any] | None = None) -> RealtimeSession:
        runner = RealtimeRunner(self._agency.entry_agent)
        merged_settings: dict[str, Any] = dict(self._base_model_settings)
        if overrides:
            for key, value in overrides.items():
                if value is not None:
                    merged_settings[key] = value

        model_settings = cast(RealtimeSessionModelSettings, merged_settings)

        session = await runner.run(
            context=MasterContext(
                thread_manager=ThreadManager(),
                agents=self._agency.source_agents,
                shared_instructions=self._agency.shared_instructions,
                user_context=dict(self._agency.user_context),
                agent_runtime_state=self._agency.runtime_state_map,
            ),
            model_config={"initial_model_settings": model_settings},
        )
        return session


def run_realtime(
    *,
    agency: Agency | RealtimeAgency,
    entry_agent: Agent | str | None = None,
    model: str = "gpt-realtime",
    voice: str | None = None,
    host: str = "0.0.0.0",
    port: int = 8000,
    turn_detection: dict[str, Any] | None = None,
    input_audio_format: str | None = None,
    output_audio_format: str | None = None,
    input_audio_noise_reduction: dict[str, Any] | None = None,
    cors_origins: list[str] | None = None,
    twilio_number: str | None = None,
    twilio_audio_format: str | None = None,
    twilio_greeting: str = "Connecting you now.",
    return_app: bool = False,
) -> FastAPI | None:
    """Launch a realtime FastAPI server backed by OpenAI's Realtime API."""

    try:
        from fastapi import FastAPI as FastAPIApp, Request as FastAPIRequest
        from fastapi.middleware.cors import CORSMiddleware as FastAPICORSMiddleware
        from fastapi.responses import PlainTextResponse as FastAPIPlainTextResponse
    except ImportError as exc:
        logger.error(
            "Realtime dependencies are missing: %s. Install agency-swarm[fastapi] to use run_realtime.",
            exc,
        )
        return None

    app = FastAPIApp()
    origins = cors_origins or ["*"]
    app.add_middleware(
        FastAPICORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    realtime_agency = _ensure_realtime_agency(agency, entry_agent)
    entry_voice = getattr(realtime_agency.entry_agent, "voice", None)
    effective_voice = voice if voice is not None else entry_voice

    base_settings = build_model_settings(
        model=model,
        voice=effective_voice,
        input_audio_format=input_audio_format,
        output_audio_format=output_audio_format,
        turn_detection=turn_detection,
        input_audio_noise_reduction=input_audio_noise_reduction,
    )
    session_factory = RealtimeSessionFactory(realtime_agency, base_settings)

    @app.websocket("/realtime")
    async def realtime_endpoint(websocket: StarletteWebSocket) -> None:
        await websocket.accept()
        print(f"[run_realtime] Accepted websocket from {websocket.client}", flush=True)
        logger.info("Realtime websocket accepted from %s", websocket.client)
        session: RealtimeSession | None = None
        try:
            try:
                session = await session_factory.create_session()
            except Exception:
                logger.exception("Failed to initialize realtime session", exc_info=True)
                await websocket.close(code=1011, reason="Failed to initialize realtime session.")
                return

            try:
                async with session as realtime_session:
                    events_task = asyncio.create_task(
                        _forward_session_events(
                            realtime_session,
                            websocket.send_text,
                            initial_voice=session_factory.default_voice,
                        )
                    )
                    try:
                        while True:
                            message = await websocket.receive()
                            message_type = message.get("type")
                            if message_type == "websocket.disconnect":
                                break
                            if message_type != "websocket.receive":
                                continue

                            text_data = message.get("text")
                            if text_data is not None:
                                await _handle_client_payload(realtime_session, text_data)
                                continue

                            bytes_data = message.get("bytes")
                            if bytes_data is not None:
                                await realtime_session.send_audio(bytes_data)
                    except WebSocketDisconnect:
                        logger.info("Realtime websocket disconnected by client %s", websocket.client)
                    except Exception:
                        logger.exception("Error while handling realtime websocket traffic", exc_info=True)
                        await websocket.close(code=1011, reason="Realtime session error.")
                    finally:
                        events_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await events_task
            finally:
                if session is not None:
                    with suppress(Exception):
                        await session.close()
        except Exception:
            logger.exception("Realtime endpoint crashed", exc_info=True)
            await websocket.close(code=1011, reason="Realtime endpoint failure.")

    listen_host = host
    listen_port = port

    if twilio_number:
        incoming_path = "/incoming-call"
        media_path = "/twilio/media-stream"
        logger.info("Twilio voice bridge enabled for %s", twilio_number)

        overrides: dict[str, Any] = {}
        if twilio_audio_format:
            overrides["input_audio_format"] = twilio_audio_format
            overrides.setdefault("output_audio_format", twilio_audio_format)
        if overrides and not overrides.get("output_audio_format") and output_audio_format:
            overrides["output_audio_format"] = output_audio_format

        @app.post(incoming_path)
        @app.get(incoming_path)
        async def incoming_call(request: FastAPIRequest) -> FastAPIPlainTextResponse:
            forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
            scheme = "https" if forwarded_proto in {"https", "wss"} else "http"
            ws_scheme = "wss" if scheme == "https" else "ws"
            host_header = request.headers.get("host", f"{listen_host}:{listen_port}")
            ws_url = f"{ws_scheme}://{host_header}{media_path}"

            twiml = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                "<Response>\n"
                f"    <Say>{twilio_greeting}</Say>\n"
                "    <Connect>\n"
                f'        <Stream url="{ws_url}" />\n'
                "    </Connect>\n"
                "</Response>"
            )
            return FastAPIPlainTextResponse(content=twiml, media_type="text/xml")

        @app.websocket(media_path)
        async def twilio_media_stream(websocket: StarletteWebSocket) -> None:
            await websocket.accept()
            try:
                session = await session_factory.create_session(overrides=overrides or None)
            except Exception:
                logger.exception("Failed to initialize realtime session for Twilio bridge", exc_info=True)
                await websocket.close(code=1011, reason="Realtime session initialization failed.")
                return
            stream_sid: str | None = None

            def _get_stream_sid() -> str | None:
                return stream_sid

            try:
                initial_voice = overrides.get("voice") if overrides else session_factory.default_voice
                async with session as realtime_session:
                    events_task = asyncio.create_task(
                        _forward_events_to_twilio(
                            realtime_session,
                            websocket,
                            _get_stream_sid,
                            initial_voice=initial_voice,
                        )
                    )
                    try:
                        while True:
                            message_text = await websocket.receive_text()
                            try:
                                payload = json.loads(message_text)
                            except json.JSONDecodeError:
                                logger.warning("Invalid Twilio payload: %s", message_text[:80])
                                continue

                            event_type = payload.get("event")
                            if event_type == "start":
                                stream_sid = payload.get("start", {}).get("streamSid", stream_sid)
                            elif event_type == "media":
                                media_payload = payload.get("media", {}).get("payload")
                                if isinstance(media_payload, str):
                                    try:
                                        audio_bytes = base64.b64decode(media_payload)
                                    except (binascii.Error, ValueError):
                                        logger.warning("Failed to decode Twilio audio payload.")
                                        continue
                                    await realtime_session.send_audio(audio_bytes)
                            elif event_type == "mark":
                                continue
                            elif event_type == "stop":
                                break
                            else:
                                logger.debug("Unhandled Twilio event: %s", event_type)
                    except WebSocketDisconnect:
                        pass
                    finally:
                        events_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await events_task
            finally:
                with suppress(Exception):
                    await session.close()

    if return_app:
        return app

    try:
        import uvicorn
    except ImportError as exc:
        logger.error("uvicorn is required to run the realtime server: %s", exc)
        return None

    logger.info("Starting realtime server at http://%s:%s", host, port)
    uvicorn.run(app, host=host, port=port)
    return None


def _ensure_realtime_agency(agency: Agency | RealtimeAgency, entry_agent: Agent | str | None) -> RealtimeAgency:
    if isinstance(agency, RealtimeAgency):
        if entry_agent is not None:
            raise ValueError("entry_agent must not be provided when a RealtimeAgency instance is supplied.")
        return agency

    if isinstance(agency, Agency):
        resolved_agent: Agent | None
        if entry_agent is None:
            resolved_agent = None
        elif isinstance(entry_agent, Agent):
            resolved_agent = entry_agent
        else:
            resolved_agent = agency.agents.get(entry_agent)
            if resolved_agent is None:
                raise ValueError(f"Agent '{entry_agent}' is not registered in the Agency.")

        return agency.to_realtime(resolved_agent)

    raise TypeError(f"Unsupported agency type: {type(agency)!r}")

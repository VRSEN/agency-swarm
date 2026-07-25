from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
from collections.abc import Mapping
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Literal, cast

from agents.realtime import RealtimeModelConfig, RealtimeRunner, RealtimeSession
from agents.realtime.config import RealtimeSessionModelSettings
from starlette.websockets import WebSocket as StarletteWebSocket, WebSocketDisconnect

from agency_swarm.agency.core import Agency
from agency_swarm.agent.core import Agent
from agency_swarm.context import MasterContext
from agency_swarm.integrations.realtime_config import (
    _normalize_provider,
    _resolve_provider_options,
    _resolve_session_voice,
    build_model_settings,
)
from agency_swarm.integrations.realtime_events import (
    _forward_events_to_twilio,
    _forward_session_events,
    _handle_client_payload,
)
from agency_swarm.realtime.agency import RealtimeAgency
from agency_swarm.utils.thread import ThreadManager

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

__all__ = ["run_realtime", "RealtimeSessionFactory", "build_model_settings"]


def _create_runner_model(provider: Literal["openai", "xai"]):
    if provider == "xai":
        from agency_swarm.realtime.xai_model import XAIRealtimeWebSocketModel

        return XAIRealtimeWebSocketModel()
    return None


class RealtimeSessionFactory:
    """Build realtime sessions for an agency.

    The voice is resolved once, before the session starts, and stays fixed for the whole call.
    Handoffs still switch the agent, its tools, and its instructions.
    """

    def __init__(
        self,
        realtime_agency: RealtimeAgency,
        base_model_settings: Mapping[str, Any],
        *,
        provider: str = "openai",
        provider_options: Mapping[str, Any] | None = None,
    ):
        self._agency = realtime_agency
        self._base_model_settings = dict(base_model_settings)
        self._provider = _normalize_provider(provider)
        _, session_voice = _resolve_session_voice(
            self._agency,
            self._provider,
            cast(str | None, self._base_model_settings.get("voice")),
        )
        if session_voice is not None:
            self._base_model_settings["voice"] = session_voice
        model_name = self._base_model_settings.get("model_name")
        self._provider_options = _resolve_provider_options(
            self._provider,
            provider_options,
            model_name=str(model_name) if model_name else None,
        )

    @property
    def session_voice(self) -> str | None:
        """Voice used for every turn of a session created by this factory."""
        voice_value = self._base_model_settings.get("voice")
        return cast(str | None, voice_value)

    async def create_session(self, overrides: dict[str, Any] | None = None) -> RealtimeSession:
        runner_model = _create_runner_model(self._provider)
        runner = RealtimeRunner(self._agency.entry_agent, model=runner_model)
        merged_settings: dict[str, Any] = dict(self._base_model_settings)
        if overrides:
            for key, value in overrides.items():
                if value is not None:
                    merged_settings[key] = value

        model_name = merged_settings.get("model_name")
        provider_options = _resolve_provider_options(
            self._provider,
            self._provider_options,
            model_name=str(model_name) if model_name else None,
        )
        model_settings = cast(RealtimeSessionModelSettings, merged_settings)
        model_config: RealtimeModelConfig = {"initial_model_settings": model_settings}
        for option_key in ("url", "api_key", "headers"):
            option_value = provider_options.get(option_key)
            if option_value:
                model_config[option_key] = option_value

        session = await runner.run(
            context=MasterContext(
                thread_manager=ThreadManager(),
                agents=self._agency.source_agents,
                shared_instructions=self._agency.shared_instructions,
                user_context=dict(self._agency.user_context),
                agent_runtime_state=self._agency.runtime_state_map,
            ),
            model_config=model_config,
        )
        return session


def run_realtime(
    *,
    agency: Agency | RealtimeAgency,
    entry_agent: Agent | str | None = None,
    model: str | None = None,
    provider: Literal["openai", "xai"] = "openai",
    provider_options: dict[str, Any] | None = None,
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
    """Launch a realtime FastAPI server backed by a supported realtime provider."""

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
    normalized_provider = _normalize_provider(provider)

    base_settings = build_model_settings(
        model=model,
        voice=voice,
        input_audio_format=input_audio_format,
        output_audio_format=output_audio_format,
        turn_detection=turn_detection,
        input_audio_noise_reduction=input_audio_noise_reduction,
        provider=normalized_provider,
    )
    session_factory = RealtimeSessionFactory(
        realtime_agency,
        base_settings,
        provider=normalized_provider,
        provider_options=provider_options,
    )

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
                async with session as realtime_session:
                    events_task = asyncio.create_task(
                        _forward_events_to_twilio(
                            realtime_session,
                            websocket,
                            _get_stream_sid,
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

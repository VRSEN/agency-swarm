from __future__ import annotations

import asyncio
import base64
import binascii
import inspect
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from typing import TYPE_CHECKING, Any, assert_never, cast

from agents import RunContextWrapper
from agents.agent import AgentBase, MCPConfig
from agents.handoffs import Handoff
from agents.realtime import RealtimeAgent, RealtimeRunner, RealtimeSession
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
from agents.realtime.model_inputs import RealtimeModelRawClientMessage, RealtimeModelSendRawMessage
from starlette.websockets import WebSocket as StarletteWebSocket, WebSocketDisconnect

from agency_swarm.agent.core import Agent
from agency_swarm.context import MasterContext
from agency_swarm.utils.thread import ThreadManager

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

__all__ = ["run_realtime", "RealtimeSessionFactory", "build_model_settings"]

if TYPE_CHECKING:
    from fastapi import FastAPI, Request


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
) -> None:
    async for event in session:
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


def _extract_agent_from_handoff(handoff: Handoff) -> Agent | None:
    on_invoke = getattr(handoff, "on_invoke_handoff", None)
    if not callable(on_invoke):
        return None
    closure = getattr(on_invoke, "__closure__", None)
    if not closure:
        return None
    for cell in closure:
        try:
            value = cell.cell_contents
        except ValueError:
            continue
        if isinstance(value, Agent):
            return value
    return None


def _wrap_is_enabled(
    is_enabled: bool | Callable[[RunContextWrapper[Any], Agent], Any],
    original_agent: Agent,
) -> bool | Callable[[RunContextWrapper[Any], AgentBase[Any]], Awaitable[bool]]:
    if not callable(is_enabled):
        return bool(is_enabled)

    async def _wrapped(ctx: RunContextWrapper[Any], _: AgentBase[Any]) -> bool:
        result = is_enabled(ctx, original_agent)
        if inspect.isawaitable(result):
            return bool(await cast(Awaitable[Any], result))
        return bool(result)

    return _wrapped


def _convert_handoff(
    original: Handoff,
    original_agent: Agent,
    realtime_agent: RealtimeAgent,
) -> Handoff:
    async def _on_invoke(ctx: RunContextWrapper[Any], input_json: str) -> RealtimeAgent:
        await original.on_invoke_handoff(ctx, input_json)
        return realtime_agent

    handoff = Handoff(
        tool_name=original.tool_name,
        tool_description=original.tool_description,
        input_json_schema=original.input_json_schema,
        on_invoke_handoff=_on_invoke,
        agent_name=realtime_agent.name,
        input_filter=original.input_filter,
        strict_json_schema=original.strict_json_schema,
        is_enabled=_wrap_is_enabled(original.is_enabled, original_agent),
    )
    return cast(Handoff, handoff)


def _build_realtime_agent_graph(starting_agent: Agent) -> tuple[RealtimeAgent, dict[str, Agent]]:
    visited: dict[int, RealtimeAgent] = {}
    agent_lookup: dict[str, Agent] = {}

    def _convert(agent: Agent) -> RealtimeAgent:
        existing = visited.get(id(agent))
        if existing:
            return existing

        instructions = agent.instructions
        realtime_instructions: str | Callable[[RunContextWrapper[Any], RealtimeAgent], Awaitable[str]] | None

        if callable(instructions):
            typed_instructions = cast(
                Callable[[RunContextWrapper[Any], Agent], Awaitable[str] | str],
                instructions,
            )

            async def _instructions(ctx: RunContextWrapper[Any], _: RealtimeAgent) -> str:
                result = typed_instructions(ctx, agent)
                if inspect.isawaitable(result):
                    return cast(str, await result)
                return cast(str, result)

            realtime_instructions = cast(
                Callable[[RunContextWrapper[Any], RealtimeAgent], Awaitable[str]],
                _instructions,
            )
        else:
            realtime_instructions = cast(str | None, instructions)

        prompt_value = agent.prompt
        prompt = prompt_value if (prompt_value is None or not callable(prompt_value)) else None

        realtime = RealtimeAgent(
            name=agent.name,
            instructions=realtime_instructions,
            handoff_description=agent.handoff_description,
            tools=list(agent.tools),
            mcp_servers=list(agent.mcp_servers),
            mcp_config=cast(MCPConfig, dict(agent.mcp_config)),
            prompt=prompt,
            output_guardrails=list(agent.output_guardrails),
        )
        visited[id(agent)] = realtime
        agent_lookup[agent.name] = agent

        converted_handoffs: list[Any] = []
        for item in agent.handoffs:
            if isinstance(item, Agent):
                converted_handoffs.append(_convert(item))
                continue
            if not isinstance(item, Handoff):
                logger.debug("Ignoring unsupported handoff entry %s on agent '%s'", item, agent.name)
                continue

            target = _extract_agent_from_handoff(item)
            if target is None:
                recipients = getattr(agent, "_subagents", None)
                if isinstance(recipients, dict):
                    target = recipients.get(item.agent_name.lower())
            if target is None:
                logger.warning(
                    "Skipping handoff '%s' on agent '%s' because the target agent could not be resolved.",
                    item.tool_name,
                    agent.name,
                )
                continue

            converted = _convert(target)
            converted_handoffs.append(_convert_handoff(item, target, converted))

        realtime.handoffs = converted_handoffs
        return realtime

    starting_realtime = _convert(starting_agent)
    return starting_realtime, agent_lookup


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
) -> None:
    async for event in session:
        stream_sid = get_stream_sid()
        if stream_sid is None:
            continue

        if isinstance(event, RealtimeAudio):
            payload = base64.b64encode(event.audio.data).decode("utf-8")
            await websocket.send_text(
                json.dumps({"event": "media", "streamSid": stream_sid, "media": {"payload": payload}})
            )
        elif isinstance(event, RealtimeAudioInterrupted):
            await websocket.send_text(json.dumps({"event": "clear", "streamSid": stream_sid}))


class RealtimeSessionFactory:
    def __init__(self, starting_agent: Agent, base_model_settings: Mapping[str, Any]):
        self._agent = starting_agent
        self._base_model_settings = dict(base_model_settings)

    async def create_session(self, overrides: dict[str, Any] | None = None) -> RealtimeSession:
        realtime_agent, agent_lookup = _build_realtime_agent_graph(self._agent)
        runner = RealtimeRunner(realtime_agent)
        merged_settings: dict[str, Any] = dict(self._base_model_settings)
        if overrides:
            for key, value in overrides.items():
                if value is not None:
                    merged_settings[key] = value

        model_settings = cast(RealtimeSessionModelSettings, merged_settings)

        session = await runner.run(
            context=MasterContext(thread_manager=ThreadManager(), agents=agent_lookup),
            model_config={"initial_model_settings": model_settings},
        )
        return session


def run_realtime(
    *,
    agent: Agent,
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
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import PlainTextResponse
    except ImportError as exc:
        logger.error(
            "Realtime dependencies are missing: %s. Install agency-swarm[fastapi] to use run_realtime.",
            exc,
        )
        return None

    app = FastAPI()
    origins = cors_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    base_settings = build_model_settings(
        model=model,
        voice=voice,
        input_audio_format=input_audio_format,
        output_audio_format=output_audio_format,
        turn_detection=turn_detection,
        input_audio_noise_reduction=input_audio_noise_reduction,
    )
    session_factory = RealtimeSessionFactory(agent, base_settings)

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
                    events_task = asyncio.create_task(_forward_session_events(realtime_session, websocket.send_text))
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
        async def incoming_call(request: Request) -> PlainTextResponse:
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
            return PlainTextResponse(content=twiml, media_type="text/xml")

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
                        _forward_events_to_twilio(realtime_session, websocket, _get_stream_sid)
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

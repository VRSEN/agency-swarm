import asyncio
import base64
import json
import logging
import struct
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, assert_never, cast

from agents.realtime import RealtimeSession, RealtimeSessionEvent
from agents.realtime.config import RealtimeUserInputMessage
from agents.realtime.items import RealtimeItem
from agents.realtime.model_inputs import (
    RealtimeModelRawClientMessage,
    RealtimeModelSendRawMessage,
    RealtimeModelSendSessionUpdate,
)
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)


class RealtimeSessionContext(Protocol):
    async def __aenter__(self) -> RealtimeSession: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...


class RealtimeSessionFactory(Protocol):
    @property
    def default_voice(self) -> str | None: ...

    async def create_session(self, overrides: dict[str, Any] | None = None) -> RealtimeSessionContext: ...


class RealtimeWebSocketManager:
    def __init__(self, session_factory: RealtimeSessionFactory):
        self._session_factory = session_factory
        self._session_voices: dict[str, str | None] = {}
        self._event_tasks: dict[str, asyncio.Task[None]] = {}

        self.active_sessions: dict[str, RealtimeSession] = {}
        self.session_contexts: dict[str, RealtimeSessionContext] = {}
        self.websockets: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str) -> bool:
        await websocket.accept()
        self.websockets[session_id] = websocket
        self._session_voices[session_id] = self._session_factory.default_voice

        try:
            session_context = await self._session_factory.create_session()
            session = await session_context.__aenter__()
        except Exception:
            logger.exception("Failed to initialize realtime session")
            with suppress(Exception):
                await websocket.close(code=1011, reason="Failed to initialize realtime session.")
            self.websockets.pop(session_id, None)
            self._session_voices.pop(session_id, None)
            return False

        self.active_sessions[session_id] = session
        self.session_contexts[session_id] = session_context

        self._event_tasks[session_id] = asyncio.create_task(self._process_events(session_id))
        return True

    async def disconnect(self, session_id: str) -> None:
        event_task = self._event_tasks.pop(session_id, None)
        if event_task is not None:
            event_task.cancel()
            with suppress(asyncio.CancelledError):
                await event_task

        session_context = self.session_contexts.pop(session_id, None)
        if session_context is not None:
            with suppress(Exception):
                await session_context.__aexit__(None, None, None)

        self.active_sessions.pop(session_id, None)
        self.websockets.pop(session_id, None)
        self._session_voices.pop(session_id, None)

    async def send_audio(self, session_id: str, audio_bytes: bytes) -> None:
        session = self.active_sessions.get(session_id)
        if session is None:
            return
        await session.send_audio(audio_bytes)

    async def send_client_event(self, session_id: str, event: dict[str, Any]) -> None:
        """Send a raw client event to the underlying realtime model."""
        session = self.active_sessions.get(session_id)
        if session is None:
            return

        await session.model.send_event(
            RealtimeModelSendRawMessage(
                message=cast(RealtimeModelRawClientMessage, event),
            )
        )

    async def send_user_message(self, session_id: str, message: RealtimeUserInputMessage) -> None:
        """Send a structured user message via the higher-level API (supports input_image)."""
        session = self.active_sessions.get(session_id)
        if session is None:
            return
        await session.send_message(message)

    async def interrupt(self, session_id: str) -> None:
        session = self.active_sessions.get(session_id)
        if session is None:
            return
        await session.interrupt()

    async def _process_events(self, session_id: str) -> None:
        session = self.active_sessions.get(session_id)
        websocket = self.websockets.get(session_id)
        if session is None or websocket is None:
            return

        try:
            async for event in session:
                if event.type == "agent_start":
                    await self._apply_voice_update(session_id, session, event)

                event_data = await self._serialize_event(event)
                await websocket.send_text(json.dumps(event_data))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error processing events for session %s", session_id)

    async def _apply_voice_update(
        self,
        session_id: str,
        session: RealtimeSession,
        event: RealtimeSessionEvent,
    ) -> None:
        desired_voice = getattr(getattr(event, "agent", None), "voice", None)
        if not desired_voice:
            return

        current_voice = self._session_voices.get(session_id)
        if desired_voice == current_voice:
            return

        try:
            await session.model.send_event(RealtimeModelSendSessionUpdate(session_settings={"voice": desired_voice}))
        except Exception:
            logger.exception("Failed to update realtime voice to %s", desired_voice)
            return

        logger.info("Updated realtime voice to %s", desired_voice)
        self._session_voices[session_id] = desired_voice

    def _sanitize_history_item(self, item: RealtimeItem) -> dict[str, Any]:
        """Remove large binary payloads from history items while keeping transcripts."""
        item_dict = item.model_dump()
        content = item_dict.get("content")
        if isinstance(content, list):
            sanitized_content: list[Any] = []
            for part in content:
                if isinstance(part, dict):
                    sanitized_part = part.copy()
                    if sanitized_part.get("type") in {"audio", "input_audio"}:
                        sanitized_part.pop("audio", None)
                    sanitized_content.append(sanitized_part)
                else:
                    sanitized_content.append(part)
            item_dict["content"] = sanitized_content
        return item_dict

    async def _serialize_event(self, event: RealtimeSessionEvent) -> dict[str, Any]:
        base_event: dict[str, Any] = {"type": event.type}

        if event.type == "agent_start":
            base_event["agent"] = event.agent.name
        elif event.type == "agent_end":
            base_event["agent"] = event.agent.name
        elif event.type == "handoff":
            base_event["from"] = event.from_agent.name
            base_event["to"] = event.to_agent.name
        elif event.type == "tool_start":
            base_event["tool"] = event.tool.name
        elif event.type == "tool_end":
            base_event["tool"] = event.tool.name
            base_event["output"] = str(event.output)
        elif event.type == "audio":
            base_event["audio"] = base64.b64encode(event.audio.data).decode("utf-8")
        elif event.type == "audio_interrupted":
            pass
        elif event.type == "audio_end":
            pass
        elif event.type == "history_updated":
            base_event["history"] = [self._sanitize_history_item(item) for item in event.history]
        elif event.type == "history_added":
            try:
                base_event["item"] = self._sanitize_history_item(event.item)
            except Exception:
                base_event["item"] = None
        elif event.type == "guardrail_tripped":
            base_event["guardrail_results"] = [{"name": result.guardrail.name} for result in event.guardrail_results]
        elif event.type == "raw_model_event":
            base_event["raw_model_event"] = {"type": event.data.type}
        elif event.type == "error":
            base_event["error"] = str(event.error) if hasattr(event, "error") else "Unknown error"
        elif event.type == "input_audio_timeout_triggered":
            pass
        else:
            assert_never(event)

        return base_event


def create_realtime_demo_app(
    session_factory: RealtimeSessionFactory,
    *,
    static_dir: Path | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Create a FastAPI app serving the realtime demo frontend + websocket bridge."""

    manager = RealtimeWebSocketManager(session_factory)
    static_path = static_dir or (Path(__file__).resolve().parent / "static")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield

    app = FastAPI(lifespan=lifespan)

    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=True,
        )

    @app.websocket("/ws/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
        connected = await manager.connect(websocket, session_id)
        if not connected:
            return

        image_buffers: dict[str, dict[str, Any]] = {}
        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                message_type = message.get("type")

                if message_type == "audio":
                    int16_data = message.get("data") or []
                    audio_bytes = struct.pack(f"{len(int16_data)}h", *int16_data)
                    await manager.send_audio(session_id, audio_bytes)
                elif message_type == "image":
                    logger.info("Received image message from client (session %s).", session_id)
                    data_url = message.get("data_url")
                    prompt_text = message.get("text") or "Please describe this image."
                    if not data_url:
                        await websocket.send_text(
                            json.dumps({"type": "error", "error": "No data_url for image message."})
                        )
                        continue

                    user_msg: RealtimeUserInputMessage = {
                        "type": "message",
                        "role": "user",
                        "content": (
                            [
                                {"type": "input_image", "image_url": data_url, "detail": "high"},
                                {"type": "input_text", "text": prompt_text},
                            ]
                            if prompt_text
                            else [{"type": "input_image", "image_url": data_url, "detail": "high"}]
                        ),
                    }
                    await manager.send_user_message(session_id, user_msg)
                    await websocket.send_text(
                        json.dumps({"type": "client_info", "info": "image_enqueued", "size": len(data_url)})
                    )
                elif message_type == "commit_audio":
                    await manager.send_client_event(session_id, {"type": "input_audio_buffer.commit"})
                elif message_type == "image_start":
                    img_id = str(message.get("id"))
                    image_buffers[img_id] = {
                        "text": message.get("text") or "Please describe this image.",
                        "chunks": [],
                    }
                    await websocket.send_text(
                        json.dumps({"type": "client_info", "info": "image_start_ack", "id": img_id})
                    )
                elif message_type == "image_chunk":
                    img_id = str(message.get("id"))
                    chunk = message.get("chunk", "")
                    if img_id in image_buffers:
                        image_buffers[img_id]["chunks"].append(chunk)
                        if len(image_buffers[img_id]["chunks"]) % 10 == 0:
                            await websocket.send_text(
                                json.dumps(
                                    {
                                        "type": "client_info",
                                        "info": "image_chunk_ack",
                                        "id": img_id,
                                        "count": len(image_buffers[img_id]["chunks"]),
                                    }
                                )
                            )
                elif message_type == "image_end":
                    img_id = str(message.get("id"))
                    buf = image_buffers.pop(img_id, None)
                    if buf is None:
                        await websocket.send_text(
                            json.dumps({"type": "error", "error": "Unknown image id for image_end."})
                        )
                        continue

                    data_url = "".join(buf["chunks"]) if buf["chunks"] else None
                    prompt_text = buf["text"]
                    if not data_url:
                        await websocket.send_text(json.dumps({"type": "error", "error": "Empty image."}))
                        continue

                    user_msg = {
                        "type": "message",
                        "role": "user",
                        "content": (
                            [
                                {"type": "input_image", "image_url": data_url, "detail": "high"},
                                {"type": "input_text", "text": prompt_text},
                            ]
                            if prompt_text
                            else [{"type": "input_image", "image_url": data_url, "detail": "high"}]
                        ),
                    }
                    await manager.send_user_message(session_id, cast(RealtimeUserInputMessage, user_msg))
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "client_info",
                                "info": "image_enqueued",
                                "id": img_id,
                                "size": len(data_url),
                            }
                        )
                    )
                elif message_type == "interrupt":
                    await manager.interrupt(session_id)
        except WebSocketDisconnect:
            pass
        finally:
            await manager.disconnect(session_id)

    app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")

    return app


if __name__ == "__main__":
    raise SystemExit("Use agency_swarm.ui.demos.realtime.RealtimeDemoLauncher.start() to run the realtime demo.")

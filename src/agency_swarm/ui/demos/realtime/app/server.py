from __future__ import annotations

import asyncio
import base64
import json
import logging
import struct
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any, assert_never

from agents.realtime import RealtimeSession, RealtimeSessionEvent
from agents.realtime.config import RealtimeUserInputMessage
from agents.realtime.model_inputs import RealtimeModelSendRawMessage
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agency_swarm.integrations.realtime import RealtimeSessionFactory

logger = logging.getLogger(__name__)


class RealtimeWebSocketManager:
    """Manage realtime websocket sessions for the demo frontend."""

    def __init__(self, session_factory: RealtimeSessionFactory):
        self._session_factory = session_factory
        self.active_sessions: dict[str, RealtimeSession] = {}
        self.session_contexts: dict[str, AbstractAsyncContextManager[RealtimeSession]] = {}
        self.websockets: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        self.websockets[session_id] = websocket

        session_context = await self._session_factory.create_session()
        session = await session_context.__aenter__()
        self.active_sessions[session_id] = session
        self.session_contexts[session_id] = session_context

        asyncio.create_task(self._process_events(session_id))

    async def disconnect(self, session_id: str) -> None:
        if session_id in self.session_contexts:
            await self.session_contexts[session_id].__aexit__(None, None, None)
            del self.session_contexts[session_id]
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
        if session_id in self.websockets:
            del self.websockets[session_id]

    async def send_audio(self, session_id: str, audio_bytes: bytes) -> None:
        session = self.active_sessions.get(session_id)
        if session:
            await session.send_audio(audio_bytes)

    async def send_client_event(self, session_id: str, event: dict[str, Any]) -> None:
        session = self.active_sessions.get(session_id)
        if not session:
            return
        await session.model.send_event(
            RealtimeModelSendRawMessage(
                message={
                    "type": event["type"],
                    "other_data": {k: v for k, v in event.items() if k != "type"},
                }
            )
        )

    async def send_user_message(self, session_id: str, message: RealtimeUserInputMessage) -> None:
        session = self.active_sessions.get(session_id)
        if session:
            await session.send_message(message)

    async def interrupt(self, session_id: str) -> None:
        session = self.active_sessions.get(session_id)
        if session:
            await session.interrupt()

    async def _process_events(self, session_id: str) -> None:
        try:
            session = self.active_sessions[session_id]
            websocket = self.websockets[session_id]

            async for event in session:
                payload = await self._serialize_event(event)
                await websocket.send_text(json.dumps(payload))
        except Exception as exc:
            logger.error("Error processing events for session %s: %s", session_id, exc)

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
            base_event["history"] = [item.model_dump(mode="json") for item in event.history]
        elif event.type == "history_added":
            try:
                base_event["item"] = event.item.model_dump(mode="json")
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


def _create_fastapi_app(
    manager: RealtimeWebSocketManager,
    *,
    static_dir: Path,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
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
        await manager.connect(websocket, session_id)
        image_buffers: dict[str, dict[str, Any]] = {}
        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)

                if message["type"] == "audio":
                    int16_data = message["data"]
                    audio_bytes = struct.pack(f"{len(int16_data)}h", *int16_data)
                    await manager.send_audio(session_id, audio_bytes)
                elif message["type"] == "image":
                    logger.info("Received image message from client (session %s).", session_id)
                    data_url = message.get("data_url")
                    prompt_text = message.get("text") or "Please describe this image."
                    if data_url:
                        logger.info(
                            "Forwarding image (structured message) to Realtime API (len=%d).",
                            len(data_url),
                        )
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
                            json.dumps(
                                {
                                    "type": "client_info",
                                    "info": "image_enqueued",
                                    "size": len(data_url),
                                }
                            )
                        )
                    else:
                        await websocket.send_text(
                            json.dumps({"type": "error", "error": "No data_url for image message."})
                        )
                elif message["type"] == "commit_audio":
                    await manager.send_client_event(session_id, {"type": "input_audio_buffer.commit"})
                elif message["type"] == "image_start":
                    img_id = str(message.get("id"))
                    image_buffers[img_id] = {
                        "text": message.get("text") or "Please describe this image.",
                        "chunks": [],
                    }
                    await websocket.send_text(
                        json.dumps({"type": "client_info", "info": "image_start_ack", "id": img_id})
                    )
                elif message["type"] == "image_chunk":
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
                elif message["type"] == "image_end":
                    img_id = str(message.get("id"))
                    buf = image_buffers.pop(img_id, None)
                    if buf is None:
                        await websocket.send_text(
                            json.dumps({"type": "error", "error": "Unknown image id for image_end."})
                        )
                    else:
                        data_url = "".join(buf["chunks"]) if buf["chunks"] else None
                        prompt_text = buf["text"]
                        if data_url:
                            logger.info(
                                "Forwarding chunked image (structured message) to Realtime API (len=%d).",
                                len(data_url),
                            )
                            user_msg2: RealtimeUserInputMessage = {
                                "type": "message",
                                "role": "user",
                                "content": (
                                    [
                                        {
                                            "type": "input_image",
                                            "image_url": data_url,
                                            "detail": "high",
                                        },
                                        {"type": "input_text", "text": prompt_text},
                                    ]
                                    if prompt_text
                                    else [
                                        {
                                            "type": "input_image",
                                            "image_url": data_url,
                                            "detail": "high",
                                        }
                                    ]
                                ),
                            }
                            await manager.send_user_message(session_id, user_msg2)
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
                        else:
                            await websocket.send_text(json.dumps({"type": "error", "error": "Empty image."}))
                elif message["type"] == "interrupt":
                    await manager.interrupt(session_id)

        except WebSocketDisconnect:
            await manager.disconnect(session_id)

    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    @app.get("/")
    async def read_index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    return app


def create_realtime_demo_app(
    session_factory: RealtimeSessionFactory,
    *,
    static_dir: Path | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Create a FastAPI app serving the realtime demo frontend + websocket bridge."""
    static_path = static_dir or Path(__file__).parent / "static"
    manager = RealtimeWebSocketManager(session_factory)
    return _create_fastapi_app(manager, static_dir=static_path, cors_origins=cors_origins)


if __name__ == "__main__":
    raise SystemExit("Use agency_swarm.ui.demos.realtime.RealtimeDemoLauncher.start() to run the realtime demo.")

"""Event translation between realtime sessions and websocket clients."""

from __future__ import annotations

import base64
import binascii
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, assert_never, cast

from agents.realtime import RealtimeSession
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
    RealtimeToolApprovalRequired,
    RealtimeToolEnd,
    RealtimeToolStart,
)
from agents.realtime.model_inputs import (
    RealtimeModelRawClientMessage,
    RealtimeModelSendRawMessage,
)
from starlette.websockets import WebSocket as StarletteWebSocket

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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


def _sanitize_history_item(item: Any) -> dict[str, Any] | None:
    item_data = _model_dump(item)
    if not isinstance(item_data, dict):
        return None

    content = item_data.get("content")
    if not isinstance(content, list):
        return item_data

    sanitized_content: list[Any] = []
    for part in content:
        if isinstance(part, dict):
            sanitized_part = dict(part)
            if sanitized_part.get("type") in {"audio", "input_audio"}:
                sanitized_part.pop("audio", None)
            sanitized_content.append(sanitized_part)
        else:
            sanitized_content.append(part)
    item_data["content"] = sanitized_content
    return item_data


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
    if isinstance(event, RealtimeToolApprovalRequired):
        return {
            "type": "tool_approval_required",
            "agent": event.agent.name,
            "tool": getattr(event.tool, "name", str(event.tool)),
            "call_id": event.call_id,
            "arguments": event.arguments,
        }
    if isinstance(event, RealtimeHistoryUpdated):
        sanitized_history = [
            item for item in (_sanitize_history_item(hist_item) for hist_item in event.history) if item
        ]
        return {
            "type": "history_updated",
            "history": sanitized_history,
        }
    if isinstance(event, RealtimeHistoryAdded):
        sanitized_item = _sanitize_history_item(event.item)
        if sanitized_item is None:
            return None
        return {
            "type": "history_added",
            "item": sanitized_item,
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

    if msg_type == "commit_audio":
        await session.model.send_event(
            RealtimeModelSendRawMessage(
                message=cast(RealtimeModelRawClientMessage, {"type": "input_audio_buffer.commit"})
            )
        )
        await session.model.send_event(
            RealtimeModelSendRawMessage(message=cast(RealtimeModelRawClientMessage, {"type": "response.create"}))
        )
        return

    other = {k: v for k, v in message.items() if k != "type"}
    raw_message: dict[str, Any] = {"type": msg_type}
    if other:
        raw_message["other_data"] = other
    client_message = cast(RealtimeModelRawClientMessage, raw_message)
    await session.model.send_event(RealtimeModelSendRawMessage(message=client_message))


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

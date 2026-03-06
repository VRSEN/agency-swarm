"""xAI realtime transport compatibility for RealtimeRunner."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from agents.realtime import OpenAIRealtimeWebSocketModel, RealtimeModelConfig

logger = logging.getLogger(__name__)

_XAI_UNSUPPORTED_CLIENT_EVENT_TYPES = {
    "conversation.item.delete",
    "conversation.item.retrieve",
}


class XAIRealtimeWebSocketModel(OpenAIRealtimeWebSocketModel):
    """Normalize xAI server events to the subset expected by openai-agents."""

    def __init__(self) -> None:
        super().__init__()
        self._xai_content_parts: dict[tuple[str, int], dict[str, object]] = {}

    async def connect(self, options: RealtimeModelConfig) -> None:
        # Use a safe default before connect; negotiated session codec may override it.
        self._set_audio_format("pcm16")
        await super().connect(options)

    async def _handle_ws_event(self, event: dict[str, Any]):
        event_type = event.get("type") if isinstance(event, dict) else None
        if event_type == "ping":
            await self._send_pong(event)
            return

        normalized = self._normalize_event(event)
        await super()._handle_ws_event(normalized)

    async def _send_raw_message(self, event: object) -> None:  # type: ignore[override]
        event_type = self._event_type_from_payload(event)
        if event_type in _XAI_UNSUPPORTED_CLIENT_EVENT_TYPES:
            logger.debug("Dropping unsupported xAI realtime client event: %s", event_type)
            return
        await super()._send_raw_message(event)  # type: ignore[arg-type]

    async def _send_pong(self, event: Mapping[str, object]) -> None:
        websocket = getattr(self, "_websocket", None)
        if websocket is None:
            return
        payload: dict[str, object] = {"type": "pong"}
        event_id = event.get("event_id")
        if isinstance(event_id, str) and event_id.strip():
            payload["event_id"] = event_id
        try:
            await websocket.send(json.dumps(payload))
        except Exception:
            logger.exception("Failed to send xAI realtime pong event")

    def _normalize_event(self, event: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(event)
        event_type = normalized.get("type")

        if event_type in {"session.created", "session.updated"}:
            session = normalized.get("session")
            if isinstance(session, Mapping):
                normalized_session = dict(session)
                normalized_session.setdefault("type", "realtime")
                tool_choice = normalized_session.get("tool_choice")
                if isinstance(tool_choice, str) and tool_choice == "not implemented":
                    normalized_session.pop("tool_choice", None)
                normalized["session"] = normalized_session
                self._set_audio_format_from_session(normalized_session)

        if event_type == "response.content_part.added":
            item_id = normalized.get("item_id")
            content_index = normalized.get("content_index")
            part = normalized.get("part")
            if isinstance(item_id, str) and isinstance(content_index, int) and isinstance(part, Mapping):
                self._xai_content_parts[(item_id, content_index)] = dict(part)

        if event_type == "response.content_part.done":
            part = normalized.get("part")
            item_id = normalized.get("item_id")
            content_index = normalized.get("content_index")
            cached_part: dict[str, object] | None = None
            if isinstance(item_id, str) and isinstance(content_index, int):
                cached = self._xai_content_parts.pop((item_id, content_index), None)
                if isinstance(cached, Mapping):
                    cached_part = dict(cached)
            if not isinstance(part, Mapping):
                normalized["part"] = cached_part if cached_part is not None else {"type": "audio"}

        if event_type in {"response.created", "response.done"}:
            response = normalized.get("response")
            if isinstance(response, Mapping):
                normalized_response = dict(response)
                if isinstance(normalized_response.get("status_details"), str):
                    normalized_response.pop("status_details", None)
                if event_type == "response.done":
                    output = normalized_response.get("output")
                    if isinstance(output, list):
                        normalized_response["output"] = [self._normalize_response_output_item(item) for item in output]
                normalized["response"] = normalized_response

        if event_type in {"response.function_call_arguments.delta", "response.function_call_arguments.done"}:
            output_index = self._coerce_int(normalized.get("output_index"))
            if output_index is None:
                output_index = self._coerce_int(normalized.get("output_item_index"))
            normalized["output_index"] = output_index if output_index is not None else 0

        if event_type == "conversation.item.input_audio_transcription.completed":
            usage = normalized.get("usage")
            if not isinstance(usage, Mapping):
                normalized["usage"] = {"type": "duration", "seconds": 0.0}

        return normalized

    @staticmethod
    def _event_type_from_payload(payload: object) -> str | None:
        if isinstance(payload, Mapping):
            event_type = payload.get("type")
            return event_type if isinstance(event_type, str) else None
        if hasattr(payload, "type"):
            event_type = payload.type
            return event_type if isinstance(event_type, str) else None
        return None

    @staticmethod
    def _coerce_int(value: object) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.isdigit() or (stripped.startswith("-") and stripped[1:].isdigit()):
                return int(stripped)
        return None

    def _normalize_response_output_item(self, item: object) -> object:
        if not isinstance(item, Mapping):
            return item

        normalized_item = dict(item)
        if normalized_item.get("type") != "message":
            return normalized_item

        role = normalized_item.get("role")
        content = normalized_item.get("content")
        if not isinstance(content, list):
            return normalized_item

        normalized_content: list[object] = []
        for part in content:
            if not isinstance(part, Mapping):
                normalized_content.append(part)
                continue
            normalized_part = dict(part)
            part_type = normalized_part.get("type")
            if role == "assistant":
                if part_type == "audio":
                    normalized_part["type"] = "output_audio"
                elif part_type == "text":
                    normalized_part["type"] = "output_text"
            elif role in {"user", "system"}:
                if part_type == "audio":
                    normalized_part["type"] = "input_audio"
                elif part_type == "text":
                    normalized_part["type"] = "input_text"
            normalized_content.append(normalized_part)

        normalized_item["content"] = normalized_content
        return normalized_item

    def _set_audio_format_from_session(self, session: Mapping[str, object]) -> None:
        audio = session.get("audio")
        if not isinstance(audio, Mapping):
            return
        output = audio.get("output")
        if not isinstance(output, Mapping):
            return
        fmt = output.get("format")
        resolved_format = self._resolve_audio_format(fmt)
        if resolved_format is None:
            return
        self._set_audio_format(resolved_format)

    def _set_audio_format(self, value: str) -> None:
        try:
            self._audio_state_tracker.set_audio_format(value)
        except Exception:
            logger.exception("Failed to set realtime audio format on model tracker")
        playback_tracker = getattr(self, "_playback_tracker", None)
        if playback_tracker is None:
            return
        try:
            playback_tracker.set_audio_format(value)
        except Exception:
            logger.exception("Failed to set realtime audio format on playback tracker")

    @staticmethod
    def _resolve_audio_format(fmt: object) -> str | None:
        if isinstance(fmt, str):
            normalized = fmt.strip().lower()
            if normalized in {"audio/pcm", "pcm16", "pcm"}:
                return "pcm16"
            if normalized in {"audio/pcmu", "pcmu", "g711_ulaw"}:
                return "g711_ulaw"
            if normalized in {"audio/pcma", "pcma", "g711_alaw"}:
                return "g711_alaw"
            return None
        if isinstance(fmt, Mapping):
            fmt_type = fmt.get("type")
            if isinstance(fmt_type, str):
                return XAIRealtimeWebSocketModel._resolve_audio_format(fmt_type)
        return None

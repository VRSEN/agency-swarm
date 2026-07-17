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
        self._xai_output_index_by_call_id: dict[str, int] = {}
        self._xai_output_index_by_item_id: dict[str, int] = {}
        self._requested_interrupt_response: bool | None = None

    async def connect(self, options: RealtimeModelConfig) -> None:
        # Use a safe default before connect; negotiated session codec may override it.
        self._set_audio_format("pcm16")
        model_settings = options.get("initial_model_settings")
        if isinstance(model_settings, Mapping):
            self._remember_requested_interrupt_response(model_settings)
        await super().connect(options)

    async def _handle_ws_event(self, event: dict[str, Any]):
        event_type = event.get("type") if isinstance(event, dict) else None
        if event_type == "ping":
            await self._send_pong(event)
            return

        normalized = self._normalize_event(event)
        if event_type in {
            "conversation.item.input_audio_transcription.completed",
            "conversation.item.truncated",
        }:
            # openai-agents emits conversation.item.retrieve for these events to
            # refresh current history item state. xAI rejects that event type.
            # Temporarily clearing current-item tracking preserves downstream
            # event handling while preventing unsupported retrieve sends.
            had_current_item_id = hasattr(self, "_current_item_id")
            current_item_id = getattr(self, "_current_item_id", None)
            if had_current_item_id:
                self._current_item_id = None
            try:
                await super()._handle_ws_event(normalized)
            finally:
                if had_current_item_id:
                    self._current_item_id = current_item_id
            return
        await super()._handle_ws_event(normalized)

    async def _send_raw_message(self, event: object) -> None:  # type: ignore[override]
        self._remember_requested_interrupt_response_from_event(event)
        event_type = self._event_type_from_payload(event)
        if event_type in _XAI_UNSUPPORTED_CLIENT_EVENT_TYPES:
            # xAI rejects these OpenAI-specific events. Skipping them prevents
            # avoidable upstream session termination during voice turns.
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
                self._restore_interrupt_response(normalized_session)
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
                        normalized_output: list[object] = []
                        for output_index, item in enumerate(output):
                            normalized_item = self._normalize_response_output_item(item)
                            normalized_output.append(normalized_item)
                            self._remember_output_item_index(output_index, normalized_item)
                        normalized_response["output"] = normalized_output
                    # Argument-delta fallbacks are response-scoped; drop stale mappings
                    # once the response is finalized to avoid unbounded cache growth.
                    self._xai_output_index_by_call_id.clear()
                    self._xai_output_index_by_item_id.clear()
                normalized["response"] = normalized_response

        if event_type in {"response.output_item.added", "response.output_item.done"}:
            item_index = self._coerce_int(normalized.get("output_index"))
            if item_index is not None:
                self._remember_output_item_index(item_index, normalized.get("item"))

        if event_type in {"response.function_call_arguments.delta", "response.function_call_arguments.done"}:
            resolved_index = self._coerce_int(normalized.get("output_index"))
            if resolved_index is None:
                resolved_index = self._coerce_int(normalized.get("output_item_index"))
            if resolved_index is None:
                call_id = normalized.get("call_id")
                if isinstance(call_id, str) and call_id.strip():
                    resolved_index = self._xai_output_index_by_call_id.get(call_id.strip())
            if resolved_index is None:
                item_id = normalized.get("item_id")
                if isinstance(item_id, str) and item_id.strip():
                    resolved_index = self._xai_output_index_by_item_id.get(item_id.strip())
            normalized["output_index"] = resolved_index if resolved_index is not None else 0

        if event_type == "conversation.item.input_audio_transcription.completed":
            normalized["usage"] = self._normalize_transcription_usage(normalized.get("usage"))

        return normalized

    def _remember_requested_interrupt_response(self, model_settings: Mapping[str, object]) -> None:
        turn_detection = model_settings.get("turn_detection")
        if not isinstance(turn_detection, Mapping):
            return
        interrupt_response = turn_detection.get("interrupt_response")
        if isinstance(interrupt_response, bool):
            self._requested_interrupt_response = interrupt_response

    def _remember_requested_interrupt_response_from_event(self, event: object) -> None:
        event_type = self._event_type_from_payload(event)
        session = self._read_field(event, "session")
        if event_type != "session.update" or session is None:
            return

        audio = self._read_field(session, "audio")
        audio_input = self._read_field(audio, "input")
        turn_detection = self._read_field(audio_input, "turn_detection")
        interrupt_response = self._read_field(turn_detection, "interrupt_response")
        if isinstance(interrupt_response, bool):
            self._requested_interrupt_response = interrupt_response
            return

        top_level_turn_detection = self._read_field(session, "turn_detection")
        interrupt_response = self._read_field(top_level_turn_detection, "interrupt_response")
        if isinstance(interrupt_response, bool):
            self._requested_interrupt_response = interrupt_response

    def _restore_interrupt_response(self, session: dict[str, Any]) -> None:
        """Re-add the requested interrupt_response flag that xAI drops from session events."""
        if self._requested_interrupt_response is None:
            return

        top_level_turn_detection = session.get("turn_detection")
        normalized_top_level_turn_detection: dict[str, Any] | None = None
        if isinstance(top_level_turn_detection, Mapping):
            normalized_top_level_turn_detection = dict(top_level_turn_detection)
            normalized_top_level_turn_detection.setdefault("interrupt_response", self._requested_interrupt_response)
            session["turn_detection"] = normalized_top_level_turn_detection

        audio = session.get("audio")
        normalized_audio = dict(audio) if isinstance(audio, Mapping) else {}
        audio_input = normalized_audio.get("input")
        normalized_input = dict(audio_input) if isinstance(audio_input, Mapping) else {}

        nested_turn_detection = normalized_input.get("turn_detection")
        if isinstance(nested_turn_detection, Mapping):
            normalized_nested_turn_detection = dict(nested_turn_detection)
        elif normalized_top_level_turn_detection is not None:
            normalized_nested_turn_detection = dict(normalized_top_level_turn_detection)
        else:
            return

        normalized_nested_turn_detection.setdefault("interrupt_response", self._requested_interrupt_response)
        normalized_input["turn_detection"] = normalized_nested_turn_detection
        normalized_audio["input"] = normalized_input
        session["audio"] = normalized_audio

    @staticmethod
    def _read_field(value: object, field: str) -> object | None:
        if isinstance(value, Mapping):
            return value.get(field)
        return getattr(value, field, None)

    def _remember_output_item_index(self, output_index: int, item: object) -> None:
        if not isinstance(item, Mapping):
            return

        item_id = item.get("id")
        if isinstance(item_id, str) and item_id.strip():
            self._xai_output_index_by_item_id[item_id.strip()] = output_index

        call_id = item.get("call_id")
        if isinstance(call_id, str) and call_id.strip():
            self._xai_output_index_by_call_id[call_id.strip()] = output_index

    @staticmethod
    def _normalize_transcription_usage(usage: object) -> dict[str, object]:
        """Coerce partial or malformed xAI transcription usage into a valid payload."""

        def _coerce_non_negative_int(value: object, *, default: int = 0) -> int:
            if isinstance(value, bool):
                return default
            if isinstance(value, int | float):
                return max(0, int(value))
            return default

        if not isinstance(usage, Mapping):
            return {"type": "tokens", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        usage_data = dict(usage)
        raw_type = usage_data.get("type")
        usage_type = raw_type.strip().lower() if isinstance(raw_type, str) else ""
        if usage_type not in {"tokens", "duration"}:
            usage_type = "duration" if isinstance(usage_data.get("seconds"), int | float) else "tokens"

        if usage_type == "duration":
            seconds_raw = usage_data.get("seconds")
            seconds = float(seconds_raw) if isinstance(seconds_raw, int | float) and seconds_raw >= 0 else 0.0
            return {"type": "duration", "seconds": seconds}

        input_tokens = _coerce_non_negative_int(usage_data.get("input_tokens"))
        output_tokens = _coerce_non_negative_int(usage_data.get("output_tokens"))
        total_tokens_raw = usage_data.get("total_tokens")
        total_tokens = (
            _coerce_non_negative_int(total_tokens_raw)
            if isinstance(total_tokens_raw, int | float) and not isinstance(total_tokens_raw, bool)
            else input_tokens + output_tokens
        )

        normalized_usage: dict[str, object] = {
            "type": "tokens",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
        input_token_details = usage_data.get("input_token_details")
        if isinstance(input_token_details, Mapping):
            normalized_details: dict[str, int] = {}
            for key in ("audio_tokens", "text_tokens"):
                value = input_token_details.get(key)
                if isinstance(value, bool):
                    continue
                if isinstance(value, int | float):
                    normalized_details[key] = max(0, int(value))
            if normalized_details:
                normalized_usage["input_token_details"] = normalized_details
        return normalized_usage

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
            normalized_item["content"] = self._fallback_message_content_for_role(role)
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

    @staticmethod
    def _fallback_message_content_for_role(role: object) -> list[dict[str, str]]:
        if role in {"user", "system"}:
            return [{"type": "input_text", "text": ""}]
        return [{"type": "output_text", "text": ""}]

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

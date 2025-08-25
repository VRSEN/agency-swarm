from __future__ import annotations

import dataclasses
import json
import logging
from typing import Any

from pydantic import BaseModel

try:
    from ag_ui.core import (
        AssistantMessage,
        BaseEvent,
        CustomEvent,
        EventType,
        FunctionCall,
        Message,
        MessagesSnapshotEvent,
        RawEvent,
        RunErrorEvent,
        TextMessageContentEvent,
        TextMessageEndEvent,
        TextMessageStartEvent,
        ToolCall,
        ToolCallArgsEvent,
        ToolCallEndEvent,
        ToolCallStartEvent,
        ToolMessage,
    )
except ImportError as exc:
    raise ImportError(
        "ag_ui.core is required for the AG-UI adapter. Install with `pip install ag-ui-protocol`."
    ) from exc

logger = logging.getLogger(__name__)


# Universal function to serialize any object to a JSON-compatible format
def serialize(obj, _visited=None):
    if _visited is None:
        _visited = set()

    # Check for circular references
    obj_id = id(obj)
    if obj_id in _visited:
        return str(obj)  # Return string representation for circular refs

    if dataclasses.is_dataclass(obj):
        _visited.add(obj_id)
        # Use __dict__ to preserve dynamically added attributes like agent and callerAgent
        result = {k: serialize(v, _visited) for k, v in obj.__dict__.items() if not k.startswith("_")}
        _visited.discard(obj_id)
        return result
    elif isinstance(obj, BaseModel):
        return {k: serialize(v, _visited) for k, v in obj.model_dump().items()}
    elif isinstance(obj, list | tuple):
        return [serialize(item, _visited) for item in obj]
    elif isinstance(obj, dict):
        return {k: serialize(v, _visited) for k, v in obj.items()}
    elif hasattr(obj, "__dict__") and not isinstance(obj, type):
        # Handle any object with __dict__ (regular dynamic objects)
        # This ensures circular reference tracking for all objects with attributes
        _visited.add(obj_id)
        result = {k: serialize(v, _visited) for k, v in obj.__dict__.items() if not k.startswith("_")}
        _visited.discard(obj_id)
        return result
    else:
        return str(obj)


class AguiAdapter:
    """
    Converts between AG-UI and other formats (e.g., OpenAI Agents SDK),
    and provides helpers for translating events and messages for AG-UI integration.

    Each instance maintains its own run state to avoid global mutable state issues.
    """

    _TOOL_TYPES = {"function_call", "file_search_call", "code_interpreter_call"}
    _TOOL_ARG_DELTA_TYPES = {
        "response.function_call_arguments.delta",
        "response.code_interpreter_call_code.delta",
    }

    def __init__(self):
        """Initialize a new AguiAdapter with clean per-instance run state."""
        # Per-instance run state to avoid global mutable state issues
        self._run_state: dict[str, dict[str, Any]] = {}

    def clear_run_state(self, run_id: str | None = None) -> None:
        """Clear run state for a specific run_id or all runs if run_id is None."""
        if run_id is None:
            self._run_state.clear()
        else:
            self._run_state.pop(run_id, None)

    def openai_to_agui_events(
        self,
        event,
        *,
        run_id: str,
    ) -> BaseEvent | list[BaseEvent] | None:
        """Convert a single OpenAI Agents SDK *StreamEvent* into one or more AG-UI events."""
        state = self._run_state.setdefault(run_id, {"call_id_by_item": {}})
        call_id_by_item: dict[str, str] = state["call_id_by_item"]

        logger.debug("Received event: %s", event)
        try:
            converted_event = None
            if getattr(event, "type", None) == "raw_response_event":
                converted_event = self._handle_raw_response(event.data, call_id_by_item)

            if getattr(event, "type", None) == "run_item_stream_event":
                converted_event = self._handle_run_item_stream(event)

            if converted_event is not None:
                return converted_event

            # Fallback: forward unknown event payloads untouched
            return RawEvent(type=EventType.RAW, event=serialize(event))

        except Exception as exc:  # pragma: no cover
            return RunErrorEvent(type=EventType.RUN_ERROR, message=str(exc))

    @staticmethod
    def agui_messages_to_chat_history(message_list: list[Message]):
        """
        Convert a list of AG-UI messages to an agency-swarm-compatible message list.
        """
        oai_messages: list[dict] = []

        for msg in message_list:
            # 1. User / system messages ---------------------------------------------------
            if msg.role in {"user", "system"}:
                oai_messages.append({"role": msg.role, "content": msg.content})
                continue

            # 2. Assistant messages -------------------------------------------------------
            if msg.role == "assistant":
                # If the assistant issued tool calls they are contained in
                # ``msg.tool_calls``.
                if getattr(msg, "tool_calls", None):
                    for tc in msg.tool_calls:  # type: ignore[attr-defined]
                        name = tc.function.name or "tool"
                        arguments = tc.function.arguments or "{}"

                        if name == "FileSearchTool":
                            args_dict = json.loads(arguments) if isinstance(arguments, str) else arguments
                            oai_messages.append(
                                {
                                    "id": msg.id,
                                    "type": "file_search_call",
                                    "queries": args_dict.get("queries", []),
                                    "status": "completed",
                                    "results": args_dict.get("results", []),
                                }
                            )
                        elif name == "CodeInterpreterTool":
                            args_dict = json.loads(arguments) if isinstance(arguments, str) else arguments
                            oai_messages.append(
                                {
                                    "id": msg.id,
                                    "type": "code_interpreter_call",
                                    "code": args_dict.get("code", ""),
                                    "container_id": args_dict.get("container_id", ""),
                                    "outputs": args_dict.get("outputs", []),
                                    "status": "completed",
                                }
                            )
                        else:
                            oai_messages.append(
                                {
                                    "id": msg.id,
                                    "call_id": tc.id,
                                    "type": "function_call",
                                    "arguments": arguments,
                                    "name": name,
                                    "status": "completed",
                                }
                            )
                else:
                    # Plain assistant response
                    oai_messages.append({"role": "assistant", "content": msg.content})
                continue

            # 3. Tool messages (results of previous tool calls) --------------------------
            if msg.role == "tool":
                oai_messages.append(
                    {
                        "call_id": msg.tool_call_id,
                        "output": msg.content,
                        "type": "function_call_output",
                    }
                )
                continue

            # 4. Developer or other roles – map to system for now ------------------------
            if msg.role == "developer":
                oai_messages.append({"role": "system", "content": msg.content})

        return oai_messages

    def _tool_meta(self, raw_item):
        """Return (call_id, tool_name, arguments) for a tool *raw_item*."""
        item_type = getattr(raw_item, "type", "")

        if item_type == "function_call":
            return (
                getattr(raw_item, "call_id", None),
                getattr(raw_item, "name", "tool"),
                getattr(raw_item, "arguments", None),
            )

        if item_type == "file_search_call":
            return (
                getattr(raw_item, "id", None),
                "FileSearchTool",
                json.dumps(
                    {
                        "queries": getattr(raw_item, "queries", None),
                        "results": getattr(raw_item, "results", None),
                    }
                ),
            )

        if item_type == "code_interpreter_call":
            return (
                getattr(raw_item, "id", None),
                "CodeInterpreterTool",
                json.dumps(
                    {
                        "code": getattr(raw_item, "code", None),
                        "container_id": getattr(raw_item, "container_id", None),
                        "outputs": getattr(raw_item, "outputs", None),
                    }
                ),
            )

        return None, None, None

    def _snapshot_event(self, item_id, call_id, tool_name, arguments):
        """Helper to build a minimal *MessagesSnapshotEvent* for a tool call."""
        return MessagesSnapshotEvent(
            type=EventType.MESSAGES_SNAPSHOT,
            messages=[
                AssistantMessage(
                    id=item_id,
                    role="assistant",
                    tool_calls=[
                        ToolCall(
                            id=call_id,
                            type="function",
                            function=FunctionCall(name=tool_name, arguments=arguments),
                        )
                    ],
                )
            ],
        )

    def _handle_raw_response(self, oe: Any, call_id_by_item: dict[str, str]) -> BaseEvent | list[BaseEvent] | None:
        """Translate low-level `raw_response_event.data` into AG-UI events."""
        etype = getattr(oe, "type", "")

        # --- Output item added -------------------------------------------------
        if etype == "response.output_item.added":
            raw_item = getattr(oe, "item", None)
            if not raw_item:
                logger.warning("raw_response_event ignored: missing item for type %s", etype)
                return None

            # Assistant / tool message start
            if getattr(raw_item, "type", "") == "message" and getattr(raw_item, "role", "") in {"assistant", "tool"}:
                msg_id = getattr(raw_item, "id", None)
                if msg_id:
                    return TextMessageStartEvent(
                        type=EventType.TEXT_MESSAGE_START,
                        message_id=msg_id,
                        role=getattr(raw_item, "role", "assistant"),
                    )
                logger.warning("raw_response_event ignored: message without id")
                return None

            # Tool call start
            if getattr(raw_item, "type", "") in self._TOOL_TYPES:
                call_id, tool_name, _ = self._tool_meta(raw_item)
                if not call_id:
                    logger.warning("raw_response_event ignored: tool call without call_id")
                    return None
                call_id_by_item[raw_item.id] = call_id
                return ToolCallStartEvent(
                    type=EventType.TOOL_CALL_START,
                    tool_call_id=call_id,
                    tool_call_name=tool_name,
                    parent_message_id=None,
                )

        # --- Text delta --------------------------------------------------------
        if etype == "response.output_text.delta":
            item_id = getattr(oe, "item_id", None)
            if item_id:
                return TextMessageContentEvent(
                    type=EventType.TEXT_MESSAGE_CONTENT,
                    message_id=item_id,
                    delta=getattr(oe, "delta", ""),
                )
            logger.warning("raw_response_event ignored: text delta without item_id")
            return None

        # --- Output item done --------------------------------------------------
        if etype == "response.output_item.done":
            raw_item = getattr(oe, "item", None)
            if not raw_item:
                logger.warning("raw_response_event ignored: output_item.done without item")
                return None

            if getattr(raw_item, "type", "") == "message":
                msg_id = getattr(raw_item, "id", None)
                if msg_id:
                    return TextMessageEndEvent(
                        type=EventType.TEXT_MESSAGE_END,
                        message_id=msg_id,
                    )
                logger.warning("raw_response_event ignored: message done without id")
                return None

            if getattr(raw_item, "type", "") in self._TOOL_TYPES:
                call_id, tool_name, arguments = self._tool_meta(raw_item)
                if not call_id:
                    logger.warning("raw_response_event ignored: tool done without call_id")
                    return None
                return [
                    ToolCallEndEvent(type=EventType.TOOL_CALL_END, tool_call_id=call_id),
                    self._snapshot_event(raw_item.id, call_id, tool_name, arguments),
                ]

        # --- Tool-argument deltas ---------------------------------------------
        if etype in self._TOOL_ARG_DELTA_TYPES:
            item_id = getattr(oe, "item_id", None)
            call_id = call_id_by_item.get(item_id) if item_id else None
            if call_id:
                return ToolCallArgsEvent(
                    type=EventType.TOOL_CALL_ARGS,
                    tool_call_id=call_id,
                    delta=getattr(oe, "delta", ""),
                )
            logger.warning("raw_response_event ignored: tool arg delta without mapping")
            return None

        logger.warning("raw_response_event ignored: no mapping for type %s", etype)
        return None

    def _handle_run_item_stream(self, event: Any) -> BaseEvent | list[BaseEvent] | None:
        """Translate higher-level run_item_stream_event into AG-UI events."""
        name = getattr(event, "name", "")

        # --- Assistant snapshot ----------------------------------------------
        if name == "message_output_created":
            output_item = getattr(event, "item", None)
            if not output_item:
                logger.warning("run_item_stream_event ignored: missing output item for %s", name)
                return None

            raw_item = getattr(output_item, "raw_item", None)
            call_id = getattr(raw_item, "id", None)
            output_content = (getattr(raw_item, "content", None) or [None])[0]
            if not output_content:
                logger.warning("run_item_stream_event ignored: output_content missing")
                return None
            output_text = getattr(output_content, "text", None)
            if not output_text:
                logger.warning("run_item_stream_event ignored: no text in output_content")
                return None

            snapshot = MessagesSnapshotEvent(
                type=EventType.MESSAGES_SNAPSHOT,
                messages=[AssistantMessage(id=call_id, role="assistant", content=output_text)],
            )

            annotations = getattr(output_content, "annotations", None)
            if annotations:
                return [
                    CustomEvent(
                        type=EventType.CUSTOM,
                        name="annotated_output",
                        value={
                            "id": call_id,
                            "role": "assistant",
                            "content": output_text,
                            "annotations": [a.model_dump() for a in annotations],
                        },
                    ),
                    snapshot,
                ]
            return [snapshot]

        # --- Tool output snapshot -------------------------------------------
        if name == "tool_output":
            output_item = getattr(event, "item", None)
            if not output_item:
                logger.warning("run_item_stream_event ignored: tool_output without item")
                return None

            raw_item = getattr(output_item, "raw_item", None)
            call_id = raw_item.get("call_id") if isinstance(raw_item, dict) else getattr(output_item, "call_id", None)
            if not call_id:
                logger.warning("run_item_stream_event ignored: tool_output without call_id")
                return None

            output_text = getattr(output_item, "output", None)
            if output_text:
                return MessagesSnapshotEvent(
                    type=EventType.MESSAGES_SNAPSHOT,
                    messages=[ToolMessage(id=call_id, role="tool", content=output_text, tool_call_id=call_id)],
                )
            logger.warning("run_item_stream_event ignored: tool_output without output text")
            return None

        logger.warning("run_item_stream_event ignored: no mapping for name %s", name)
        return None

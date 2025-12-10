"""
ChatKit Adapter for Agency Swarm.

Converts OpenAI Agents SDK streaming events to ChatKit ThreadStreamEvent format.
This enables Agency Swarm agents to be served via OpenAI's ChatKit UI.

ChatKit event types:
- thread.created - New thread created
- thread.item.added - New item (message, tool call) added
- thread.item.updated - Item updated (streaming text deltas)
- thread.item.done - Item finalized

ThreadItem types:
- assistant_message - Assistant response
- user_message - User input
- client_tool_call - Tool invocation
"""

import json
import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class ChatkitAdapter:
    """
    Converts between OpenAI Agents SDK events and ChatKit ThreadStreamEvent format.

    Each instance maintains its own run state to track message IDs and tool calls.
    """

    _TOOL_TYPES = {"function_call", "file_search_call", "code_interpreter_call"}
    _TOOL_ARG_DELTA_TYPES = {
        "response.function_call_arguments.delta",
        "response.code_interpreter_call_code.delta",
    }

    def __init__(self) -> None:
        """Initialize a new ChatkitAdapter with clean per-instance state."""
        self._run_state: dict[str, dict[str, Any]] = {}
        self._message_counter = 0

    def clear_run_state(self, run_id: str | None = None) -> None:
        """Clear run state for a specific run_id or all runs if run_id is None."""
        if run_id is None:
            self._run_state.clear()
        else:
            self._run_state.pop(run_id, None)

    def _generate_item_id(self) -> str:
        """Generate a unique item ID for ChatKit items."""
        self._message_counter += 1
        return f"item_{self._message_counter}_{uuid.uuid4().hex[:8]}"

    def _create_thread_created_event(self, thread_id: str) -> dict[str, Any]:
        """Create a thread.created event."""
        return {
            "type": "thread.created",
            "thread": {
                "id": thread_id,
                "created_at": int(time.time()),
                "metadata": {},
            },
        }

    def _create_item_added_event(
        self,
        item_id: str,
        item_type: str,
        content: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a thread.item.added event."""
        item: dict[str, Any] = {
            "id": item_id,
            "type": item_type,
            "created_at": int(time.time()),
        }
        if content:
            item.update(content)
        return {
            "type": "thread.item.added",
            "item": item,
        }

    def _create_item_updated_event(
        self,
        item_id: str,
        update: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a thread.item.updated event for streaming content."""
        return {
            "type": "thread.item.updated",
            "item_id": item_id,
            "update": update,
        }

    def _create_item_done_event(self, item_id: str) -> dict[str, Any]:
        """Create a thread.item.done event to finalize an item."""
        return {
            "type": "thread.item.done",
            "item_id": item_id,
        }

    def _create_assistant_message_item(
        self,
        item_id: str,
        text: str = "",
    ) -> dict[str, Any]:
        """Create an assistant_message item structure."""
        return {
            "content": [
                {
                    "type": "output_text",
                    "text": text,
                    "annotations": [],
                }
            ],
        }

    def _create_tool_call_item(
        self,
        call_id: str,
        name: str,
        arguments: str = "{}",
        status: str = "in_progress",
        output: str | None = None,
    ) -> dict[str, Any]:
        """Create a client_tool_call item structure."""
        item: dict[str, Any] = {
            "call_id": call_id,
            "name": name,
            "arguments": arguments,
            "status": status,
        }
        if output is not None:
            item["output"] = output
        return item

    def openai_to_chatkit_events(
        self,
        event: Any,
        *,
        run_id: str,
        thread_id: str,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        """
        Convert a single OpenAI Agents SDK StreamEvent into one or more ChatKit events.

        Args:
            event: The OpenAI Agents SDK event to convert
            run_id: Unique identifier for this run
            thread_id: The ChatKit thread ID

        Returns:
            A ChatKit event dict, list of event dicts, or None if no conversion
        """
        state = self._run_state.setdefault(
            run_id,
            {
                "call_id_by_item": {},
                "item_id_by_call": {},
                "current_message_id": None,
                "accumulated_text": {},
            },
        )
        call_id_by_item: dict[str, str] = state["call_id_by_item"]
        item_id_by_call: dict[str, str] = state["item_id_by_call"]
        accumulated_text: dict[str, str] = state["accumulated_text"]

        logger.debug("Received event: %s", event)
        try:
            converted_event = None

            if getattr(event, "type", None) == "raw_response_event":
                converted_event = self._handle_raw_response(
                    event.data,
                    call_id_by_item,
                    item_id_by_call,
                    accumulated_text,
                    state,
                )

            if getattr(event, "type", None) == "run_item_stream_event":
                converted_event = self._handle_run_item_stream(
                    event,
                    state,
                    accumulated_text,
                )

            return converted_event

        except Exception as exc:
            logger.exception("Error converting event to ChatKit format")
            return {
                "type": "thread.error",
                "error": {"message": str(exc)},
            }

    def _handle_raw_response(
        self,
        oe: Any,
        call_id_by_item: dict[str, str],
        item_id_by_call: dict[str, str],
        accumulated_text: dict[str, str],
        state: dict[str, Any],
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        """Translate raw_response_event.data into ChatKit events."""
        etype = getattr(oe, "type", "")

        # --- Output item added -------------------------------------------------
        if etype == "response.output_item.added":
            raw_item = getattr(oe, "item", None)
            if not raw_item:
                logger.warning("raw_response_event ignored: missing item for type %s", etype)
                return None

            # Assistant message start
            if getattr(raw_item, "type", "") == "message" and getattr(raw_item, "role", "") == "assistant":
                msg_id = getattr(raw_item, "id", None) or self._generate_item_id()
                state["current_message_id"] = msg_id
                accumulated_text[msg_id] = ""
                return self._create_item_added_event(
                    msg_id,
                    "assistant_message",
                    self._create_assistant_message_item(msg_id, ""),
                )

            # Tool call start
            if getattr(raw_item, "type", "") in self._TOOL_TYPES:
                call_id, tool_name, _ = self._tool_meta(raw_item)
                if not call_id:
                    logger.warning("raw_response_event ignored: tool call without call_id")
                    return None
                item_id = self._generate_item_id()
                call_id_by_item[raw_item.id] = call_id
                item_id_by_call[call_id] = item_id
                return self._create_item_added_event(
                    item_id,
                    "client_tool_call",
                    self._create_tool_call_item(call_id, tool_name or "tool", "{}", "in_progress"),
                )

        # --- Text delta --------------------------------------------------------
        if etype == "response.output_text.delta":
            raw_item_id: str | None = getattr(oe, "item_id", None)
            delta_text: str = getattr(oe, "delta", "")
            if raw_item_id and delta_text:
                # Use the current message ID from state
                current_msg_id: str = state.get("current_message_id") or raw_item_id
                accumulated_text[current_msg_id] = accumulated_text.get(current_msg_id, "") + delta_text
                return self._create_item_updated_event(
                    current_msg_id,
                    {
                        "type": "assistant_message.content_part.text_delta",
                        "content_index": 0,
                        "delta": delta_text,
                    },
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
                msg_id = state.get("current_message_id") or getattr(raw_item, "id", None)
                if msg_id:
                    return self._create_item_done_event(msg_id)
                logger.warning("raw_response_event ignored: message done without id")
                return None

            if getattr(raw_item, "type", "") in self._TOOL_TYPES:
                call_id, tool_name, arguments = self._tool_meta(raw_item)
                if not call_id:
                    logger.warning("raw_response_event ignored: tool done without call_id")
                    return None
                chatkit_item_id: str | None = item_id_by_call.get(call_id)
                if chatkit_item_id:
                    return [
                        self._create_item_updated_event(
                            chatkit_item_id,
                            {
                                "type": "client_tool_call.arguments_done",
                                "arguments": arguments or "{}",
                            },
                        ),
                        self._create_item_done_event(chatkit_item_id),
                    ]
                return None

        # --- Tool-argument deltas ---------------------------------------------
        if etype in self._TOOL_ARG_DELTA_TYPES:
            tool_delta_item_id: str | None = getattr(oe, "item_id", None)
            tool_call_id: str | None = call_id_by_item.get(tool_delta_item_id) if tool_delta_item_id else None
            if tool_call_id:
                chatkit_tool_item_id: str | None = item_id_by_call.get(tool_call_id)
                if chatkit_tool_item_id:
                    return self._create_item_updated_event(
                        chatkit_tool_item_id,
                        {
                            "type": "client_tool_call.arguments_delta",
                            "delta": getattr(oe, "delta", ""),
                        },
                    )
            logger.warning("raw_response_event ignored: tool arg delta without mapping")
            return None

        return None

    def _handle_run_item_stream(
        self,
        event: Any,
        state: dict[str, Any],
        accumulated_text: dict[str, str],
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        """Translate run_item_stream_event into ChatKit events."""
        name = getattr(event, "name", "")
        item_id_by_call: dict[str, str] = state["item_id_by_call"]

        # --- Assistant message complete ----------------------------------------
        if name == "message_output_created":
            output_item = getattr(event, "item", None)
            if not output_item:
                logger.warning("run_item_stream_event ignored: missing output item for %s", name)
                return None

            raw_item = getattr(output_item, "raw_item", None)
            msg_id: str | None = state.get("current_message_id") or getattr(raw_item, "id", None)
            output_content = (getattr(raw_item, "content", None) or [None])[0]
            if not output_content or not msg_id:
                return None

            output_text = getattr(output_content, "text", None)
            if not output_text:
                return None

            # Final message snapshot
            return self._create_item_updated_event(
                msg_id,
                {
                    "type": "assistant_message.content_part.done",
                    "content_index": 0,
                    "content": {
                        "type": "output_text",
                        "text": output_text,
                        "annotations": [],
                    },
                },
            )

        # --- Tool output -------------------------------------------------------
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
            item_id = item_id_by_call.get(call_id)
            if item_id and output_text:
                return self._create_item_updated_event(
                    item_id,
                    {
                        "type": "client_tool_call.output",
                        "output": output_text,
                        "status": "completed",
                    },
                )
            return None

        return None

    def _tool_meta(self, raw_item: Any) -> tuple[str | None, str | None, str | None]:
        """Return (call_id, tool_name, arguments) for a tool raw_item."""
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

    @staticmethod
    def chatkit_messages_to_chat_history(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Convert a list of ChatKit thread items to Agency Swarm chat history format.

        Args:
            items: List of ChatKit thread items (user_message, assistant_message, etc.)

        Returns:
            List of messages in Agency Swarm's flat chat history format
        """
        messages: list[dict[str, Any]] = []

        for item in items:
            item_type = item.get("type", "")

            # User message
            if item_type == "user_message":
                content = item.get("content", [])
                text = ""
                for part in content:
                    if part.get("type") == "input_text":
                        text += part.get("text", "")
                messages.append({"role": "user", "content": text})

            # Assistant message
            elif item_type == "assistant_message":
                content = item.get("content", [])
                text = ""
                for part in content:
                    if part.get("type") == "output_text":
                        text += part.get("text", "")
                messages.append({"role": "assistant", "content": text})

            # Tool call
            elif item_type == "client_tool_call":
                call_id = item.get("call_id", item.get("id", ""))
                name = item.get("name", "tool")
                arguments = item.get("arguments", "{}")
                status = item.get("status", "completed")
                messages.append(
                    {
                        "id": item.get("id", call_id),
                        "call_id": call_id,
                        "type": "function_call",
                        "arguments": arguments,
                        "name": name,
                        "status": status,
                    }
                )
                # If tool has output, add it
                if item.get("output"):
                    messages.append(
                        {
                            "call_id": call_id,
                            "output": item["output"],
                            "type": "function_call_output",
                        }
                    )

        return messages

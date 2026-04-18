"""
ChatKit endpoint handlers for Agency Swarm.

Provides FastAPI endpoint handlers that implement the ChatKit protocol,
enabling OpenAI's ChatKit UI to communicate with Agency Swarm agents.
"""

import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from typing import Any

from agents import ModelSettings, RunConfig
from chatkit.types import InferenceOptions
from fastapi import Depends, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from agency_swarm import Agency
from agency_swarm.tools.mcp_manager import attach_persistent_mcp_servers
from agency_swarm.ui.core.chatkit_adapter import ChatkitAdapter

logger = logging.getLogger(__name__)


class ChatkitUserInput(BaseModel):
    """User input for ChatKit messages."""

    content: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[str] = Field(default_factory=list)
    quoted_text: str | None = None
    inference_options: InferenceOptions = Field(default_factory=InferenceOptions)


class ChatkitParams(BaseModel):
    """Parameters for ChatKit requests."""

    thread_id: str | None = None
    input: ChatkitUserInput | None = None


class ChatkitRequest(BaseModel):
    """Request model for ChatKit protocol.

    ChatKit sends requests with a 'type' field indicating the operation:
    - threads.create: Create new thread with initial message
    - threads.add_user_message: Add message to existing thread
    - threads.get_by_id: Get thread by ID (non-streaming)
    - items.list: List items in a thread (non-streaming)
    """

    type: str = "threads.create"
    params: ChatkitParams = Field(default_factory=ChatkitParams)
    context: dict[str, Any] = Field(default_factory=dict)


@dataclass
class _ChatkitThreadState:
    """In-memory thread state for the ChatKit endpoint."""

    thread: dict[str, Any]
    items: list[dict[str, Any]] = field(default_factory=list)


class _ChatkitThreadStore:
    """Small in-memory store modeled after the official ChatKit starter app."""

    def __init__(self) -> None:
        self._threads: dict[str, _ChatkitThreadState] = {}

    def ensure_thread(self, thread_id: str) -> tuple[_ChatkitThreadState, bool]:
        """Return thread state, creating it if needed."""
        existing = self._threads.get(thread_id)
        if existing is not None:
            return existing, False

        state = _ChatkitThreadState(
            thread={
                "id": thread_id,
                "created_at": int(time.time()),
                "metadata": {},
            }
        )
        self._threads[thread_id] = state
        return state, True

    def get_thread(self, thread_id: str) -> _ChatkitThreadState | None:
        """Return thread state if present."""
        return self._threads.get(thread_id)

    def list_threads(self, *, limit: int = 20, after: str | None = None, order: str = "desc") -> dict[str, Any]:
        """Return paginated thread metadata."""
        rows = [state.thread for state in self._threads.values()]
        return self._paginate(rows, after=after, limit=limit, order=order)

    def list_items(
        self,
        thread_id: str,
        *,
        limit: int = 20,
        after: str | None = None,
        order: str = "desc",
    ) -> dict[str, Any]:
        """Return paginated items for a thread."""
        state = self.get_thread(thread_id)
        if state is None:
            return {"data": [], "has_more": False}

        rows = [dict(item) for item in state.items]
        return self._paginate(rows, after=after, limit=limit, order=order)

    def get_history_items(self, thread_id: str, *, exclude_item_id: str | None = None) -> list[dict[str, Any]]:
        """Return stored items in ascending order for history reconstruction."""
        state = self.get_thread(thread_id)
        if state is None:
            return []

        indexed_items = [
            (index, dict(item)) for index, item in enumerate(state.items) if item.get("id") != exclude_item_id
        ]
        return [
            item
            for _, item in sorted(
                indexed_items,
                key=lambda entry: (entry[1].get("created_at", 0), entry[0]),
            )
        ]

    def save_item(self, thread_id: str, item: dict[str, Any]) -> None:
        """Insert or replace a finalized thread item."""
        state, _ = self.ensure_thread(thread_id)
        item_id = item.get("id")
        if not item_id:
            return

        for idx, existing in enumerate(state.items):
            if existing.get("id") == item_id:
                state.items[idx] = dict(item)
                return

        state.items.append(dict(item))

    def set_previous_response_id(self, thread_id: str, previous_response_id: str) -> None:
        """Persist the last OpenAI response id on the thread metadata."""
        state, _ = self.ensure_thread(thread_id)
        metadata = state.thread.setdefault("metadata", {})
        metadata["previous_response_id"] = previous_response_id

    def get_previous_response_id(self, thread_id: str) -> str | None:
        """Return the stored previous_response_id for a thread, if any."""
        state = self.get_thread(thread_id)
        if state is None:
            return None

        value = state.thread.get("metadata", {}).get("previous_response_id")
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _paginate(
        rows: list[dict[str, Any]],
        *,
        after: str | None,
        limit: int,
        order: str,
    ) -> dict[str, Any]:
        """Paginate rows by created_at and id."""
        limit = max(limit, 1)
        sorted_rows = [
            row
            for _, row in sorted(
                enumerate(rows),
                key=lambda entry: (entry[1].get("created_at", 0), entry[0]),
                reverse=order == "desc",
            )
        ]
        start = 0
        if after:
            for idx, row in enumerate(sorted_rows):
                if row.get("id") == after:
                    start = idx + 1
                    break
        data = sorted_rows[start : start + limit]
        has_more = start + limit < len(sorted_rows)
        next_after = data[-1].get("id") if has_more and data else None
        payload: dict[str, Any] = {"data": data, "has_more": has_more}
        if next_after:
            payload["after"] = next_after
        return payload


def _serialize_event(event: dict[str, Any]) -> bytes:
    """Serialize a ChatKit event to SSE format."""
    return f"data: {json.dumps(event)}\n\n".encode()


def _extract_user_message(user_input: dict[str, Any]) -> str:
    """Flatten ChatKit input content parts into a single text string."""
    text_parts: list[str] = []
    for part in user_input.get("content", []):
        if not isinstance(part, dict):
            continue
        if part.get("type") == "input_text":
            text_parts.append(part.get("text", ""))
        elif "text" in part:
            text_parts.append(part.get("text", ""))
    return "".join(text_parts)


def _create_user_item(thread_id: str, user_input: dict[str, Any], user_message: str) -> dict[str, Any]:
    """Build the persisted user_message item for a ChatKit thread."""
    return {
        "id": f"user_{uuid.uuid4().hex[:8]}",
        "type": "user_message",
        "thread_id": thread_id,
        "created_at": int(time.time()),
        "content": [{"type": "input_text", "text": user_message}],
        "attachments": user_input.get("attachments", []),
        "quoted_text": user_input.get("quoted_text"),
        "inference_options": user_input.get("inference_options", {}),
    }


def _create_run_config_override(user_input: dict[str, Any]) -> RunConfig | None:
    """Translate ChatKit inference options into an Agents SDK RunConfig override."""
    inference_options = user_input.get("inference_options")
    if hasattr(inference_options, "model_dump"):
        inference_options = inference_options.model_dump(exclude_none=True)
    if not isinstance(inference_options, dict):
        return None

    model_name = inference_options.get("model")
    tool_choice = inference_options.get("tool_choice")
    model_settings_kwargs: dict[str, Any] = {}

    if isinstance(tool_choice, dict):
        tool_choice_id = tool_choice.get("id")
        if isinstance(tool_choice_id, str) and tool_choice_id:
            model_settings_kwargs["tool_choice"] = tool_choice_id

    run_config_kwargs: dict[str, Any] = {}
    if isinstance(model_name, str) and model_name:
        run_config_kwargs["model"] = model_name
    if model_settings_kwargs:
        run_config_kwargs["model_settings"] = ModelSettings(**model_settings_kwargs)

    if not run_config_kwargs:
        return None
    return RunConfig(**run_config_kwargs)


async def _wait_for_final_result(stream: Any) -> Any:
    """Return the final streaming result when the stream wrapper exposes it."""
    wait_final_result = getattr(stream, "wait_final_result", None)
    if callable(wait_final_result):
        return await wait_final_result()
    return getattr(stream, "final_result", None)


def make_chatkit_endpoint(
    request_model: type[ChatkitRequest],
    agency_factory: Callable[..., Agency],
    verify_token: Callable[..., Any],
) -> Callable[..., Any]:
    """Create a ChatKit protocol endpoint handler.

    This endpoint handles requests from ChatKit UI and streams responses
    using the ChatKit ThreadStreamEvent protocol.

    Args:
        request_model: Pydantic model for request validation (ChatkitRequest)
        agency_factory: Factory function that returns an Agency instance
        verify_token: Token verification dependency

    Returns:
        FastAPI endpoint handler function
    """
    _ = request_model  # Mark as used
    thread_store = _ChatkitThreadStore()

    async def handler(
        request: Request,
        token: str = Depends(verify_token),
    ) -> Response:
        """Handle ChatKit protocol requests."""
        body = await request.body()
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {}

        req_type = data.get("type", "threads.create")
        params = data.get("params", {})
        context = data.get("metadata")
        if not isinstance(context, dict):
            context = data.get("context", {})
        if not isinstance(context, dict):
            context = {}
        requested_thread_id = params.get("thread_id")

        # Handle non-streaming requests
        if req_type == "threads.list":
            payload = thread_store.list_threads(
                limit=int(params.get("limit", 20) or 20),
                after=params.get("after"),
                order=params.get("order", "desc"),
            )
            return Response(content=json.dumps(payload), media_type="application/json")

        if req_type == "threads.get_by_id":
            if not requested_thread_id:
                return Response(content=json.dumps({"error": "thread_id is required"}), media_type="application/json")

            thread_state = thread_store.get_thread(requested_thread_id)
            if thread_state is None:
                return Response(
                    status_code=404, content=json.dumps({"error": "Thread not found"}), media_type="application/json"
                )

            payload = dict(thread_state.thread)
            payload["items"] = thread_store.list_items(requested_thread_id, limit=int(params.get("limit", 20) or 20))
            return Response(content=json.dumps(payload), media_type="application/json")

        if req_type == "items.list":
            if not requested_thread_id:
                return Response(content=json.dumps({"data": [], "has_more": False}), media_type="application/json")

            payload = thread_store.list_items(
                requested_thread_id,
                limit=int(params.get("limit", 20) or 20),
                after=params.get("after"),
                order=params.get("order", "desc"),
            )
            return Response(content=json.dumps(payload), media_type="application/json")

        if req_type == "items.feedback":
            return Response(content=json.dumps({}), media_type="application/json")

        thread_id = requested_thread_id or str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        thread_state, created_now = thread_store.ensure_thread(thread_id)
        is_new_thread = req_type == "threads.create" or created_now

        # Extract user message
        user_input = params.get("input", {}) or {}
        user_message = _extract_user_message(user_input)

        if not user_message:
            return Response(
                content=json.dumps({"thread_id": thread_id, "status": "no_input"}),
                media_type="application/json",
            )

        user_item = _create_user_item(thread_id, user_input, user_message)
        previous_response_id = thread_store.get_previous_response_id(thread_id)
        run_config_override = _create_run_config_override(user_input)

        async def event_generator() -> AsyncGenerator[bytes]:
            """Generate ChatKit SSE events from Agency Swarm responses."""
            adapter = ChatkitAdapter()

            if is_new_thread:
                yield _serialize_event({"type": "thread.created", "thread": thread_state.thread})

            thread_store.save_item(thread_id, user_item)
            yield _serialize_event({"type": "thread.item.done", "item": user_item})

            history_items = [user_item] if previous_response_id else thread_store.get_history_items(thread_id)
            agent_input = await ChatkitAdapter.chatkit_messages_to_agent_input(history_items)
            agency = agency_factory()
            await attach_persistent_mcp_servers(agency)

            stream = None
            try:
                stream = agency.get_response_stream(
                    message=agent_input,
                    context_override=context if context else None,
                    previous_response_id=previous_response_id,
                    auto_previous_response_id=True,
                    run_config_override=run_config_override,
                )
                async for event in stream:
                    chatkit_event = adapter.openai_to_chatkit_events(event, run_id=run_id, thread_id=thread_id)
                    if chatkit_event:
                        events = chatkit_event if isinstance(chatkit_event, list) else [chatkit_event]
                        for evt in events:
                            if evt.get("type") == "thread.item.done":
                                item = evt.get("item")
                                if isinstance(item, dict):
                                    thread_store.save_item(thread_id, item)
                            yield _serialize_event(evt)

                final_result = await _wait_for_final_result(stream)
                last_response_id = getattr(final_result, "last_response_id", None)
                if isinstance(last_response_id, str) and last_response_id:
                    thread_store.set_previous_response_id(thread_id, last_response_id)

            except Exception as exc:
                logger.exception("Error during ChatKit streaming")
                yield _serialize_event({"type": "thread.error", "error": {"message": str(exc)}})

            yield _serialize_event({"type": "thread.run.completed", "thread_id": thread_id, "run_id": run_id})

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return handler

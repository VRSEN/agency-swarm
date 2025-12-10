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
from typing import Any

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


def _serialize_event(event: dict[str, Any]) -> bytes:
    """Serialize a ChatKit event to SSE format."""
    return f"data: {json.dumps(event)}\n\n".encode()


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
        context = data.get("context", {})

        # Handle non-streaming requests
        if req_type in ("threads.get_by_id", "threads.list", "items.list", "items.feedback"):
            return Response(
                content=json.dumps({"data": [], "has_more": False}),
                media_type="application/json",
            )

        thread_id = params.get("thread_id") or str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        is_new_thread = req_type == "threads.create"

        # Extract user message
        user_message = ""
        user_input = params.get("input", {})
        if user_input:
            content_list = user_input.get("content", [])
            for part in content_list:
                if isinstance(part, dict):
                    if part.get("type") == "input_text":
                        user_message += part.get("text", "")
                    elif "text" in part:
                        user_message += part.get("text", "")

        if not user_message:
            return Response(
                content=json.dumps({"thread_id": thread_id, "status": "no_input"}),
                media_type="application/json",
            )

        agency = agency_factory()
        await attach_persistent_mcp_servers(agency)

        async def event_generator() -> AsyncGenerator[bytes]:
            """Generate ChatKit SSE events from Agency Swarm responses."""
            adapter = ChatkitAdapter()

            if is_new_thread:
                yield _serialize_event(adapter._create_thread_created_event(thread_id))

            user_item_id = f"user_{uuid.uuid4().hex[:8]}"
            user_item = {
                "id": user_item_id,
                "type": "user_message",
                "thread_id": thread_id,
                "created_at": int(time.time()),
                "content": [{"type": "input_text", "text": user_message}],
                "attachments": [],
            }
            yield _serialize_event({"type": "thread.item.done", "item": user_item})

            try:
                async for event in agency.get_response_stream(
                    message=user_message,
                    context_override=context if context else None,
                ):
                    chatkit_event = adapter.openai_to_chatkit_events(event, run_id=run_id, thread_id=thread_id)
                    if chatkit_event:
                        events = chatkit_event if isinstance(chatkit_event, list) else [chatkit_event]
                        for evt in events:
                            yield _serialize_event(evt)

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

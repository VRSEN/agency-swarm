"""Active streaming run registry and cancel endpoint factory."""

import asyncio
import logging
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agency_swarm import Agency
from agency_swarm.agent.execution_stream_response import StreamingRunResponse
from agency_swarm.integrations.fastapi_utils.message_builders import _normalize_new_messages_for_client
from agency_swarm.messages import MessageFilter

# Keep the pre-split logger name so log records are unchanged.
logger = logging.getLogger("agency_swarm.integrations.fastapi_utils.endpoint_handlers")


@dataclass
class ActiveRun:
    """Tracks an active streaming run for cancellation support."""

    stream: StreamingRunResponse
    agency: Agency
    initial_message_count: int
    cancelled: bool = field(default=False)
    cancel_mode: str | None = field(default=None)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    done_event: asyncio.Event = field(default_factory=asyncio.Event)


class ActiveRunRegistry:
    """Async-safe registry for active runs so cancel endpoints see local state."""

    def __init__(self) -> None:
        self._runs: dict[str, ActiveRun] = {}
        self._lock = asyncio.Lock()

    async def register(self, run_id: str, run: ActiveRun) -> None:
        async with self._lock:
            self._runs[run_id] = run

    async def get(self, run_id: str) -> ActiveRun | None:
        async with self._lock:
            return self._runs.get(run_id)

    async def mark_cancelled(self, run_id: str, cancel_mode: str) -> ActiveRun | None:
        async with self._lock:
            run = self._runs.get(run_id)
            if run is not None:
                run.cancelled = True
                run.cancel_mode = cancel_mode
                run.cancel_event.set()
            return run

    async def finish(self, run_id: str) -> ActiveRun | None:
        async with self._lock:
            run = self._runs.pop(run_id, None)
        if run is not None:
            run.done_event.set()
        return run


def get_verify_token(app_token):
    auto_error = app_token is not None and app_token != ""
    security = HTTPBearer(auto_error=auto_error)

    async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):  # noqa: B008
        if app_token is None or app_token == "":
            return None
        if not credentials or credentials.credentials != app_token:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return credentials.credentials

    return verify_token


# Cancel streaming endpoint
def make_cancel_endpoint(request_model, verify_token, run_registry: ActiveRunRegistry):
    """Create a cancel endpoint that stops an active streaming run.

    Returns the messages generated before cancellation.
    """

    async def handler(request: request_model, token: str = Depends(verify_token)):
        run_id = request.run_id
        cancel_mode = request.cancel_mode or "immediate"

        active_run = await run_registry.mark_cancelled(run_id, cancel_mode)
        if active_run is None:
            raise HTTPException(
                status_code=404,
                detail=f"Run '{run_id}' not found or already completed",
            )

        # Mark as cancelled and call cancel on the stream
        active_run.stream.cancel(mode=cancel_mode)
        logger.info(f"Cancelled run {run_id} via cancel endpoint (mode={cancel_mode})")

        # Wait for the streaming worker to finish draining events
        timed_out = False
        try:
            await asyncio.wait_for(active_run.done_event.wait(), timeout=60)
        except TimeoutError:
            logger.warning("Timed out waiting for run %s to finish cancellation (mode=%s)", run_id, cancel_mode)
            timed_out = True
        # Get messages generated before cancel
        all_messages = active_run.agency.thread_manager.get_all_messages()
        new_messages = all_messages[active_run.initial_message_count :]
        # Remove duplicates, filter unwanted types, and remove orphaned tool calls/outputs
        filtered_messages = MessageFilter.remove_duplicates(new_messages)
        filtered_messages = MessageFilter.filter_messages(filtered_messages)
        filtered_messages = MessageFilter.remove_orphaned_messages(filtered_messages)
        filtered_messages = _normalize_new_messages_for_client(filtered_messages)

        return {
            "ok": not timed_out,
            "run_id": run_id,
            "cancelled": not timed_out,
            "cancel_mode": cancel_mode,
            "new_messages": filtered_messages,
            "timed_out": timed_out,
        }

    return handler

"""
Utilities for managing streaming events across nested agent calls.

This module provides infrastructure for collecting and forwarding events
from sub-agents to maintain full visibility during streaming operations.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


def add_agent_name_to_event(
    event: Any,
    agent_name: str,
    caller_agent: str | None = None,
    agent_run_id: str | None = None,
    parent_run_id: str | None = None,
) -> Any:
    """Non-destructively add agent/caller and attach run/call IDs to an event.

    - Does NOT overwrite existing `agent`/`callerAgent` (preserves SDK attribution e.g. handoffs)
    - Adds `agent_run_id`/`parent_run_id` when applicable
    - Extracts and sets `call_id`/`item_id` for downstream correlation
    """
    if isinstance(event, dict):
        event.setdefault("agent", agent_name)
        event.setdefault("callerAgent", caller_agent)
        if "type" in event:
            if agent_run_id and "agent_run_id" not in event:
                event["agent_run_id"] = agent_run_id
            if parent_run_id and "parent_run_id" not in event:
                event["parent_run_id"] = parent_run_id
    elif hasattr(event, "__dict__"):
        if not hasattr(event, "agent"):
            try:
                event.agent = agent_name
            except Exception:
                pass
        if not hasattr(event, "callerAgent"):
            try:
                event.callerAgent = caller_agent
            except Exception:
                pass
        if hasattr(event, "type"):
            if agent_run_id and not hasattr(event, "agent_run_id"):
                try:
                    event.agent_run_id = agent_run_id
                except Exception:
                    pass
            if parent_run_id and not hasattr(event, "parent_run_id"):
                try:
                    event.parent_run_id = parent_run_id
                except Exception:
                    pass

    # Extract and propagate call_id if present in the event structure
    call_id = None
    item_id = None

    # Check for call_id in various locations within the event
    if hasattr(event, "data"):
        data = event.data

        # Check for item_id on delta events (for function arguments, text, etc.)
        if hasattr(data, "item_id"):
            item_id = data.item_id

        # Check in data.item for various ID fields
        if hasattr(data, "item"):
            item = data.item
            # Check for call_id directly
            if hasattr(item, "call_id"):
                call_id = item.call_id
            # Also check for id field (some items have both id and call_id)
            elif hasattr(item, "id"):
                # For function calls, the id field can serve as call_id
                call_id = item.id

    # Check in event.item structure (for run_item_stream_event)
    if not call_id and hasattr(event, "item") and event.item:
        item = event.item
        # Check for call_id directly
        if hasattr(item, "call_id"):
            call_id = item.call_id
        # For tool_call_item events, check raw_item
        elif hasattr(item, "type") and item.type == "tool_call_item":
            if hasattr(item, "raw_item"):
                raw = item.raw_item
                # Check both call_id and id fields
                if hasattr(raw, "call_id"):
                    call_id = raw.call_id
                elif hasattr(raw, "id"):
                    call_id = raw.id

    # Add call_id to root level if found
    if call_id:
        if isinstance(event, dict):
            event["call_id"] = call_id
        elif hasattr(event, "__dict__"):
            event.call_id = call_id

    # Add item_id to root level if found (useful for correlating delta events)
    if item_id:
        if isinstance(event, dict):
            event["item_id"] = item_id
        elif hasattr(event, "__dict__"):
            event.item_id = item_id

    return event


@dataclass
class StreamingContext:
    """Context for managing event streaming across nested agent calls."""

    event_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    is_streaming: bool = True
    _merge_task: asyncio.Task | None = None

    async def put_event(self, event: Any) -> None:
        """Add an event to the queue."""
        await self.event_queue.put(event)

    async def get_event(self) -> Any:
        """Get an event from the queue."""
        return await self.event_queue.get()

    def stop(self) -> None:
        """Signal that streaming is complete."""
        self.event_queue.put_nowait(None)  # Sentinel value


class EventStreamMerger:
    """Merges events from multiple sources during streaming operations."""

    def __init__(self):
        self.streaming_context: StreamingContext | None = None

    @asynccontextmanager
    async def create_streaming_context(self):
        """Create a new streaming context for collecting events."""
        self.streaming_context = StreamingContext()
        try:
            yield self.streaming_context
        finally:
            if self.streaming_context:
                self.streaming_context.stop()
                self.streaming_context = None

    async def merge_streams(
        self,
        primary_stream: AsyncGenerator[Any],
        context: StreamingContext,
    ) -> AsyncGenerator[Any]:
        """
        Merge events from the primary stream and the context's event queue.

        This allows sub-agent events to be interleaved with the main agent's events.
        """
        # Create tasks for both sources
        primary_task = asyncio.create_task(self._consume_primary(primary_stream))
        queue_task = asyncio.create_task(self._consume_queue(context))

        pending = {primary_task, queue_task}

        try:
            while pending:
                # Wait for the first task to produce an event
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)

                for task in done:
                    try:
                        event = task.result()
                        if event is None:
                            # Stream ended
                            if task == primary_task:
                                logger.debug("Primary stream ended")
                                # Cancel queue task if primary is done
                                queue_task.cancel()
                                return
                            else:
                                logger.debug("Queue stream ended")
                                # Queue ended, but primary might still have events
                                continue
                        else:
                            yield event

                            # Restart the task to get the next event
                            if task == primary_task:
                                primary_task = asyncio.create_task(self._consume_primary(primary_stream))
                                pending.add(primary_task)
                            else:
                                queue_task = asyncio.create_task(self._consume_queue(context))
                                pending.add(queue_task)
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logger.error(f"Error in stream merger: {e}")
                        raise
        finally:
            # Clean up any remaining tasks
            for task in pending:
                task.cancel()

    async def _consume_primary(self, stream: AsyncGenerator[Any]) -> Any:
        """Consume one event from the primary stream."""
        try:
            return await stream.__anext__()
        except StopAsyncIteration:
            return None

    async def _consume_queue(self, context: StreamingContext) -> Any:
        """Consume one event from the queue."""
        event = await context.get_event()
        return event  # None is sentinel for end

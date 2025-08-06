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


def add_agent_name_to_event(event: Any, agent_name: str, caller_agent: str | None = None) -> Any:
    """Add agent name and caller to a streaming event.

    Args:
        event: The streaming event (dict or object)
        agent_name: Name of the agent to add to the event
        caller_agent: Name of the calling agent (None for user)

    Returns:
        The event with agent, callerAgent, and call_id (when available) added
    """
    # Add agent metadata
    if isinstance(event, dict):
        event["agent"] = agent_name
        event["callerAgent"] = caller_agent
    elif hasattr(event, "__dict__"):
        # For object-like events, add as attributes
        event.agent = agent_name
        event.callerAgent = caller_agent

    # Extract and propagate call_id if present in the event structure
    call_id = None

    # Check for call_id in various locations within the event
    if hasattr(event, "data"):
        data = event.data
        # Check in data.item.call_id
        if hasattr(data, "item") and hasattr(data.item, "call_id"):
            call_id = data.item.call_id

    # Check in event.item structure
    if not call_id and hasattr(event, "item") and event.item:
        item = event.item
        # Check for call_id directly
        if hasattr(item, "call_id"):
            call_id = item.call_id
        # For tool_call_item events, check raw_item.id
        elif hasattr(item, "type") and item.type == "tool_call_item":
            if hasattr(item, "raw_item") and hasattr(item.raw_item, "id"):
                call_id = item.raw_item.id

    # Add call_id to root level if found
    if call_id:
        if isinstance(event, dict):
            event["call_id"] = call_id
        elif hasattr(event, "__dict__"):
            event.call_id = call_id

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


# Global instance for the agency
event_stream_merger = EventStreamMerger()

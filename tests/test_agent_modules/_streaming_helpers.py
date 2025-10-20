import asyncio
from collections.abc import Iterable, Sequence
from unittest.mock import MagicMock

from agents import RunResultStreaming
from agents.items import MessageOutputItem
from agents.stream_events import RunItemStreamEvent
from openai.types.responses import ResponseOutputMessage, ResponseOutputText


def build_message_item(message_id: str, text: str) -> MessageOutputItem:
    return MessageOutputItem(
        raw_item=ResponseOutputMessage(
            id=message_id,
            content=[ResponseOutputText(text=text, type="output_text", annotations=[])],
            role="assistant",
            status="completed",
            type="message",
        ),
        type="message_output_item",
        agent=None,
    )


def make_stream_result(
    events: Sequence[RunItemStreamEvent | dict],
    *,
    history_snapshot: Iterable[dict] | None = None,
    final_output: str | None = None,
    delay_first_event: bool = False,
) -> RunResultStreaming:
    """Create a lightweight RunResultStreaming stub with minimal ceremony."""

    async def _event_stream():
        if delay_first_event:
            await asyncio.sleep(0)
        for event in events:
            yield event

    history = list(history_snapshot or [])
    for event in events:
        if isinstance(event, RunItemStreamEvent) and hasattr(event.item, "to_input_item"):
            history.append(event.item.to_input_item())

    result = MagicMock(spec=RunResultStreaming)
    result.stream_events.side_effect = _event_stream
    result.to_input_list.return_value = history
    result.final_output = final_output
    result.cancel.return_value = None
    return result

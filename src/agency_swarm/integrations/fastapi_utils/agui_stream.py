from collections.abc import AsyncGenerator
from typing import Any

from ag_ui.core import EventType, MessagesSnapshotEvent
from ag_ui.encoder import EventEncoder

from agency_swarm.ui.core.agui_adapter import AguiAdapter


async def encode_agui_stream_events(
    *,
    agency: Any,
    request: Any,
    encoder: EventEncoder,
    combined_file_ids: list[str],
) -> AsyncGenerator[str]:
    """Encode AG-UI events while preserving server-side snapshot state."""
    agui_adapter = AguiAdapter()
    snapshot_messages = [message.model_dump() for message in request.messages]
    async for event in agency.get_response_stream(
        message=request.messages[-1].content,
        context_override=request.user_context,
        additional_instructions=request.additional_instructions,
        file_ids=combined_file_ids or None,
    ):
        agui_event = agui_adapter.openai_to_agui_events(event, run_id=request.run_id)
        if agui_event:
            agui_events = agui_event if isinstance(agui_event, list) else [agui_event]
            emitted_snapshot = False
            for agui_evt in agui_events:
                if isinstance(agui_evt, MessagesSnapshotEvent):
                    emitted_snapshot = True
                    snapshot_messages.append(agui_evt.messages[0].model_dump())
                    yield encoder.encode(
                        MessagesSnapshotEvent(type=EventType.MESSAGES_SNAPSHOT, messages=snapshot_messages)
                    )
                else:
                    yield encoder.encode(agui_evt)
            if emitted_snapshot:
                continue

        state_snapshot = agui_adapter.message_snapshot_event(event)
        if state_snapshot is not None:
            snapshot_messages.append(state_snapshot.messages[0].model_dump())

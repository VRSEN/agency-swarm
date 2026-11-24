import hashlib
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from agents import TResponseInputItem
from agents.items import MessageOutputItem, RunItem
from agents.models.fake_id import FAKE_RESPONSES_ID

from agency_swarm.messages import MessageFilter, MessageFormatter
from agency_swarm.streaming.id_normalizer import StreamIdNormalizer
from agency_swarm.utils.citation_extractor import extract_direct_file_annotations

logger = logging.getLogger(__name__)

_GUARDRAIL_CONTROL_MESSAGE_ORIGINS = {
    "input_guardrail_error",
    "input_guardrail_message",
    "output_guardrail_error",
}

# Type alias for metadata stored during streaming.
# Tuple of (agent_name, agent_run_id, caller_name, emission_timestamp).
# Used to match RunItems between streaming and final persistence.
ItemMetadata = tuple[str, str, str | None, int]

# Key types for by_item dictionary:
# - int: Python object id() for identity matching
# - (str, str | None): (message_id, item_type) for OpenAI recreated objects
# - ("call", str, str | None): (marker, call_id, item_type) for tool calls
MetadataKey = int | tuple[str, str | None] | tuple[str, str, str | None]

# Hash keys use a queue structure to handle identical content items.
HashKey = tuple[str, str | None]  # (content_hash, item_type)


@dataclass
class StreamMetadataStore:
    """Container for metadata collected during streaming.

    Stores metadata by various keys for matching items between streaming
    and final persistence. Hash-based matching uses queues to preserve
    metadata for all identical items.
    """

    by_item: dict[MetadataKey, ItemMetadata] = field(default_factory=dict)
    hash_queues: dict[HashKey, deque[ItemMetadata]] = field(default_factory=dict)


def _compute_content_hash(run_item: RunItem) -> str | None:
    """Compute a hash of the item's content for matching when IDs fail.

    Used as fallback for LiteLLM where message IDs are __fake_id__ and
    object identity is not preserved (e.g., reasoning_item, handoff_output_item).
    """
    try:
        raw_item = cast(Any, run_item.raw_item)

        item_type = getattr(run_item, "type", None)
        content_parts: list[str] = [str(item_type)]

        # ReasoningItem: has summary field (list of SummaryText)
        if hasattr(raw_item, "summary"):
            summary = raw_item.summary
            if isinstance(summary, list):
                for part in summary:
                    if hasattr(part, "text"):
                        content_parts.append(str(part.text))
            elif summary:
                content_parts.append(str(summary))

        # MessageOutputItem: has content field (list of ResponseOutputText etc.)
        if hasattr(raw_item, "content") and isinstance(raw_item.content, list):
            for content_item in raw_item.content:
                if hasattr(content_item, "text"):
                    content_parts.append(str(content_item.text))

        # HandoffOutputItem: has output field (JSON string or dict)
        if hasattr(raw_item, "output"):
            content_parts.append(str(raw_item.output))
        elif isinstance(raw_item, dict) and "output" in raw_item:
            content_parts.append(str(raw_item["output"]))

        # ToolCallItem: has name and arguments
        if hasattr(raw_item, "name"):
            content_parts.append(str(raw_item.name))
        if hasattr(raw_item, "arguments"):
            content_parts.append(str(raw_item.arguments))

        # Fallback: try generic text field
        if len(content_parts) == 1 and hasattr(raw_item, "text"):
            content_parts.append(str(raw_item.text))

        if len(content_parts) == 1:
            return None  # No content to hash

        content_str = "|".join(content_parts)
        return hashlib.sha256(content_str.encode()).hexdigest()[:16]
    except Exception:
        return None


if TYPE_CHECKING:
    from agency_swarm.agent.agency_session import AgencySession
    from agency_swarm.agent.core import AgencyContext, Agent
    from agency_swarm.context import MasterContext


def _extract_item_ids(run_item: Any) -> tuple[str | None, str | None, str | None]:
    """Return (item_id, call_id, item_type) from a RunItem and its raw_item."""
    raw_item = getattr(run_item, "raw_item", None)
    item_id = getattr(run_item, "id", None)
    if not item_id:
        item_id = raw_item.get("id") if isinstance(raw_item, dict) else getattr(raw_item, "id", None)
    call_id = getattr(run_item, "call_id", None)
    if not call_id:
        call_id = raw_item.get("call_id") if isinstance(raw_item, dict) else getattr(raw_item, "call_id", None)
    item_type = getattr(run_item, "type", None)
    return (
        item_id if isinstance(item_id, str) and item_id else None,
        call_id if isinstance(call_id, str) and call_id else None,
        item_type if isinstance(item_type, str) else None,
    )


def _update_names_from_event(
    event: Any,
    current_stream_agent_name: str,
    current_agent_run_id: str,
    master_context_for_run: "MasterContext",
) -> tuple[str, str]:
    """Derive agent name and run id updates from a streaming event."""
    if getattr(event, "_forwarded", False):
        return current_stream_agent_name, current_agent_run_id

    try:
        if getattr(event, "type", None) == "run_item_stream_event":
            if getattr(event, "name", None) == "handoff_occured":
                item = getattr(event, "item", None)
                target = MessageFormatter.extract_handoff_target_name(item) if item is not None else None
                if target:
                    current_stream_agent_name = target
                    current_agent_run_id = f"agent_run_{uuid.uuid4().hex}"
                    master_context_for_run._current_agent_run_id = current_agent_run_id
        elif getattr(event, "type", None) == "agent_updated_stream_event":
            new_agent = getattr(event, "new_agent", None)
            if new_agent is not None and hasattr(new_agent, "name") and new_agent.name:
                event_id = getattr(event, "id", None)
                if isinstance(event_id, str) and event_id:
                    current_agent_run_id = event_id
                elif new_agent.name != current_stream_agent_name:
                    current_agent_run_id = f"agent_run_{uuid.uuid4().hex}"
                current_stream_agent_name = new_agent.name
                master_context_for_run._current_agent_run_id = current_agent_run_id
    except Exception:
        pass

    return current_stream_agent_name, current_agent_run_id


def _resolve_caller_agent(payload: Any, default: str | None) -> str | None:
    """Extract caller agent metadata from heterogeneous payload structures."""
    caller_agent: str | None
    if isinstance(payload, dict):
        caller_agent = payload.get("callerAgent")
    else:
        caller_agent = getattr(payload, "callerAgent", None)
    if isinstance(caller_agent, str) and caller_agent:
        return caller_agent
    return default


def _persist_run_item_if_needed(
    event: Any,
    *,
    agent: "Agent",
    sender_name: str | None,
    parent_run_id: str | None,
    run_trace_id: str,
    current_stream_agent_name: str,
    current_agent_run_id: str,
    agency_context: "AgencyContext | None",
    metadata_store: StreamMetadataStore,
    session: "AgencySession | None" = None,
) -> None:
    """Persist run item to thread manager with agency metadata if applicable."""
    run_item_obj = getattr(event, "item", None)
    if run_item_obj is None:
        return

    is_forwarded = getattr(event, "_forwarded", False)
    if not agency_context or not agency_context.thread_manager:
        return

    item_dict = cast(
        TResponseInputItem,
        MessageFormatter.strip_agency_metadata([run_item_obj.to_input_item()])[0],
    )
    if item_dict and isinstance(run_item_obj, MessageOutputItem):
        single_citation_map = extract_direct_file_annotations([run_item_obj], agent_name=agent.name)
        MessageFormatter.add_citations_to_message(run_item_obj, item_dict, single_citation_map, is_streaming=True)

    caller_for_event = _resolve_caller_agent(event, sender_name)

    formatted_item = MessageFormatter.add_agency_metadata(
        item_dict,  # type: ignore[arg-type]
        agent=current_stream_agent_name,
        caller_agent=caller_for_event,
        agent_run_id=current_agent_run_id,
        parent_run_id=parent_run_id,
        run_trace_id=run_trace_id,
        history_protocol=MessageFormatter.resolve_history_protocol_for_agent_name(
            current_stream_agent_name,
            default_agent=agent,
            agency_context=agency_context,
        ),
    )

    # Skip per-event persistence for forwarded items (they're persisted by their originating agent)
    # but continue to capture metadata below for final persistence matching. claim_streamed_item
    # decides which writer stores this turn item: False means the session already saved it
    # (turn-end saves can race the event queue); True records the claim so a later session
    # save of the same item skips it. Claim only when about to write so filtered items never
    # consume the counters.
    if not is_forwarded and not MessageFilter.should_filter(formatted_item):
        if session is None or session.claim_streamed_item(item_dict):
            agency_context.thread_manager.add_messages([formatted_item])  # type: ignore[arg-type]

    # Capture the timestamp that was just generated for this item
    _ts = formatted_item.get("timestamp")
    emission_timestamp: int = _ts if isinstance(_ts, int) else int(time.time() * 1_000_000)

    # Prefer agent name from the item itself (more reliable than current_stream_agent_name
    # which depends on event parsing). Fall back to current_stream_agent_name if not available.
    item_agent = getattr(run_item_obj, "agent", None)
    item_agent_name = getattr(item_agent, "name", None) if item_agent is not None else None
    if not isinstance(item_agent_name, str) or not item_agent_name:
        item_agent_name = current_stream_agent_name

    # Track metadata by object id, real message id, call_id, and content-hash queue.
    obj_id = id(run_item_obj)
    item_id, call_id, item_type = _extract_item_ids(run_item_obj)
    metadata = (item_agent_name, current_agent_run_id, caller_for_event, emission_timestamp)

    metadata_store.by_item[obj_id] = metadata
    if item_id and item_id != FAKE_RESPONSES_ID:
        metadata_store.by_item[(item_id, item_type)] = metadata
    if call_id:
        metadata_store.by_item[("call", call_id, item_type)] = metadata
    if (not item_id or item_id == FAKE_RESPONSES_ID) and not call_id:
        content_hash = _compute_content_hash(run_item_obj)
        if content_hash:
            metadata_store.hash_queues.setdefault((content_hash, item_type), deque()).append(metadata)


def _persist_streamed_items(
    *,
    streaming_result: Any,
    metadata_store: StreamMetadataStore,
    collected_items: list[RunItem],
    agent: "Agent",
    sender_name: str | None,
    parent_run_id: str | None,
    run_trace_id: str,
    fallback_agent_run_id: str,
    agency_context: "AgencyContext",
    initial_saved_count: int,
    session_agent_run_id: str | None = None,
) -> None:
    """Persist sanitized items after streaming completes."""
    if agency_context.thread_manager is None:
        return

    new_items: list[RunItem] = getattr(streaming_result, "new_items", None) or []
    if not new_items:
        if collected_items:
            logger.warning(
                "streaming_result.new_items is empty or missing - using %d collected streamed item(s) "
                "for final persistence.",
                len(collected_items),
            )
            new_items = collected_items
        else:
            if hasattr(agency_context.thread_manager, "persist"):
                agency_context.thread_manager.persist()
            logger.warning(
                "streaming_result.new_items is empty or missing - skipping final item persistence. "
                "This may indicate a guardrail trip (expected) or an SDK issue (unexpected)."
            )
            return
    assistant_messages = [item for item in collected_items if isinstance(item, MessageOutputItem)]
    citations_by_message = (
        extract_direct_file_annotations(assistant_messages, agent_name=agent.name) if assistant_messages else {}
    )

    items_to_save: list[TResponseInputItem] = []
    current_agent_name = agent.name
    current_agent_run_id = fallback_agent_run_id

    for run_item in new_items:
        item_dict = run_item.to_input_item()
        if not isinstance(item_dict, dict):
            continue
        item_copy: dict[str, Any] = dict(item_dict)

        obj_id = id(run_item)
        item_id, call_id, item_type = _extract_item_ids(run_item)
        matched_meta = metadata_store.by_item.get(obj_id)
        if matched_meta is None and item_id and item_id != FAKE_RESPONSES_ID:
            matched_meta = metadata_store.by_item.get((item_id, item_type))
        if matched_meta is None and call_id:
            matched_meta = metadata_store.by_item.get(("call", call_id, item_type))
        if matched_meta is None:
            content_hash = _compute_content_hash(run_item)
            if content_hash:
                queue = metadata_store.hash_queues.get((content_hash, item_type))
                if queue:
                    matched_meta = queue.popleft()

        if matched_meta is not None:
            current_agent_name, current_agent_run_id, caller_name, emission_timestamp = matched_meta
        else:
            logger.debug(f"Metadata fallback for unmatched item type={item_type} - using persist-time timestamp")
            caller_name = _resolve_caller_agent(item_copy, sender_name)
            current_agent_name = agent.name
            current_agent_run_id = fallback_agent_run_id
            emission_timestamp = int(time.time() * 1_000_000)

        item_payload = cast(TResponseInputItem, item_copy)

        if isinstance(run_item, MessageOutputItem):
            MessageFormatter.add_citations_to_message(run_item, item_payload, citations_by_message, is_streaming=True)

        formatted_item: TResponseInputItem = MessageFormatter.add_agency_metadata(
            item_payload,
            agent=current_agent_name,
            caller_agent=caller_name,
            agent_run_id=current_agent_run_id,
            parent_run_id=parent_run_id,
            run_trace_id=run_trace_id,
            history_protocol=MessageFormatter.resolve_history_protocol_for_agent_name(
                current_agent_name,
                default_agent=agent,
                agency_context=agency_context,
            ),
            timestamp=emission_timestamp,
        )
        items_to_save.append(formatted_item)

        if getattr(run_item, "type", None) == "handoff_output_item":
            target = MessageFormatter.extract_handoff_target_name(run_item)
            if target:
                current_agent_name = target
        else:
            current_agent_name = agent.name
            current_agent_run_id = fallback_agent_run_id

    filtered_items = [item for item in items_to_save if not MessageFilter.should_filter(item)]
    if not filtered_items:
        return

    normalizer = StreamIdNormalizer()
    filtered_items = normalizer.normalize_message_dicts(filtered_items)

    synthetic_keys_to_replace: set[tuple[str, str]] = {
        (origin, str(item.get("content")))
        for item in filtered_items
        if isinstance(origin := item.get("message_origin"), str)
    }

    timestamps_by_tool_id: dict[str, int] = {
        tool_call_id: ts
        for item in filtered_items
        if isinstance(item, dict)
        and isinstance(tool_call_id := item.get("call_id"), str)
        and isinstance(ts := item.get("timestamp"), int)
    }

    hosted_tool_outputs = MessageFormatter.extract_hosted_tool_results(
        agent, collected_items, sender_name, timestamps_by_tool_id
    )
    if hosted_tool_outputs:
        for hosted_item in MessageFilter.filter_messages(hosted_tool_outputs):  # type: ignore[arg-type]
            origin = hosted_item.get("message_origin")
            key = (origin, str(hosted_item.get("content"))) if isinstance(origin, str) else None
            if key and key in synthetic_keys_to_replace:
                continue
            filtered_items.append(hosted_item)
            if key:
                synthetic_keys_to_replace.add(key)

    try:
        existing_messages = agency_context.thread_manager.get_all_messages()
    except Exception:
        existing_messages = []

    initial_index = min(max(initial_saved_count, 0), len(existing_messages))
    preserved_prefix = existing_messages[:initial_index]
    mutable_tail = existing_messages[initial_index:]

    # Replace items persisted mid-stream under any run_id emitted in this attempt,
    # including the session's initial agent_run_id (which stays constant across handoffs/retries).
    run_ids_to_replace: set[str] = {
        run_id for item in filtered_items if isinstance(run_id := item.get("agent_run_id"), str)
    }
    if isinstance(session_agent_run_id, str) and session_agent_run_id:
        run_ids_to_replace.add(session_agent_run_id)

    keys_to_replace: set[tuple[str, str | None, str | None]] = set()
    for item in filtered_items:
        saved_id = item.get("id")
        saved_call_id = item.get("call_id")
        raw_type = item.get("type")
        saved_type = raw_type if isinstance(raw_type, str) else None
        if isinstance(saved_id, str) and saved_id and saved_id != FAKE_RESPONSES_ID:
            keys_to_replace.add(("id", saved_id, saved_type))
        if isinstance(saved_call_id, str) and saved_call_id:
            keys_to_replace.add(("call", saved_call_id, saved_type))

    rebuilt_tail: list[TResponseInputItem] = []
    for existing_item in mutable_tail:
        existing_key = _message_key(existing_item)
        run_id = existing_item.get("agent_run_id")
        if existing_key is not None and existing_key in keys_to_replace:
            continue
        if isinstance(run_id, str) and run_id in run_ids_to_replace and not _is_initiating_input_message(existing_item):
            continue
        origin = existing_item.get("message_origin")
        if isinstance(origin, str):
            synthetic_key = (origin, str(existing_item.get("content")))
            if synthetic_key in synthetic_keys_to_replace:
                continue
        rebuilt_tail.append(existing_item)

    # Remove orphaned items (e.g., function_call without output) before saving
    combined_new_items = rebuilt_tail + filtered_items
    combined_new_items = MessageFilter.remove_orphaned_messages(combined_new_items)

    sanitized_history = preserved_prefix + combined_new_items

    agency_context.thread_manager.replace_messages(sanitized_history)
    agency_context.thread_manager.persist()


def _message_key(message: TResponseInputItem) -> tuple[str, str | None, str | None] | None:
    if not isinstance(message, dict):
        return None

    # Skip placeholder ID from LiteLLM/Chat Completions models
    message_id = message.get("id")
    if isinstance(message_id, str) and message_id and message_id != FAKE_RESPONSES_ID:
        return ("id", message_id, message.get("type"))

    call_id = message.get("call_id")
    if isinstance(call_id, str) and call_id:
        return ("call", call_id, message.get("type"))

    return None


def _is_initiating_input_message(message: TResponseInputItem) -> bool:
    if not isinstance(message, dict):
        return False
    if message.get("message_origin") in _GUARDRAIL_CONTROL_MESSAGE_ORIGINS:
        return False
    return message.get("type") == "message" and message.get("role") in {"user", "system", "developer"}

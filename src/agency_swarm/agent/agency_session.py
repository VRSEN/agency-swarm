"""Agents SDK ``Session`` adapter over the agency's shared flat message store.

The SDK owns the standard session lifecycle once a ``Session`` is passed to
``Runner.run``/``run_streamed``: it prepends history via ``get_items``, persists
turn input and generated items via ``add_items``, rewinds on retries via
``pop_item`` and clears via ``clear_session``. ``AgencySession`` maps that
linear per-conversation contract onto Agency Swarm's semantics:

- One flat ``MessageStore`` is shared by every agent in an agency. Each session
  instance is bound to one ``(agent, sender_name)`` pair, so ``get_items``
  returns exactly the slice that pair is allowed to see (the shared user
  thread for user runs, the bidirectional pair thread for agent-to-agent).
- Stored items carry agency metadata (agent, callerAgent, run ids, protocol).
  ``get_items`` strips it and applies the model-facing sanitizers, while
  ``add_items`` enriches items before they are stored, tracking handoffs so
  items generated after a transfer are attributed to the target agent.
- ``persist_items`` reconciles against this session's own write counters
  (bounded, sequence-based — never a store scan): input persisted at
  construction, items the per-stream-event writer
  (``execution_stream_persistence``) already claimed this run, and session
  writes the stream writer must skip when a turn-end save races the event
  queue. Identical items from other slices, turns or runs always persist.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any, cast

from agents import TResponseInputItem
from agents.memory import SessionABC, SessionInputCallback

from agency_swarm.messages import MessageFilter, MessageFormatter
from agency_swarm.messages.response_input_sanitizer import sanitize_store_false_responses_input
from agency_swarm.streaming.id_normalizer import StreamIdNormalizer
from agency_swarm.utils.citation_extractor import extract_file_citations_from_input_item
from agency_swarm.utils.thread import ThreadManager

if TYPE_CHECKING:
    from agents import RunConfig

    from agency_swarm.agent.context_types import AgencyContext
    from agency_swarm.agent.core import Agent

logger = logging.getLogger(__name__)

# Internal tag used to partition the sanitized history/new boundary back apart.
_HISTORY_TAG = "_agency_swarm_history_tag"

# Keys excluded when fingerprinting items for dedupe. Agency metadata and
# volatile envelope fields (id, status) differ between writers of the same
# logical item; message_origin stays so synthetic markers remain distinct.
_FINGERPRINT_EXCLUDED_KEYS = frozenset(
    field for field in MessageFormatter.metadata_fields if field != "message_origin"
) | {"id", "status"}


def _item_fingerprint(item: Any) -> str | None:
    """Content fingerprint of an item ignoring agency metadata and volatile ids."""
    if not isinstance(item, dict):
        return None
    body = {key: value for key, value in item.items() if key not in _FINGERPRINT_EXCLUDED_KEYS}
    return json.dumps(body, sort_keys=True, default=str)


def _canonical_fingerprint(item: Any) -> str | None:
    """Canonical dedupe fingerprint across an item's raw/model/stored forms.

    ``add_agency_metadata`` injects ``type="message"`` when absent and ephemeral
    content markers are stripped for the model view, so both transforms are
    mirrored here: raw input, its sanitized model view and its persisted
    save-form all share this fingerprint.
    """
    stripped = MessageFormatter.strip_ephemeral_content(item, drop_parts=False)
    if not isinstance(stripped, dict):
        return _item_fingerprint(stripped)
    body = stripped if stripped.get("type") is not None else {**stripped, "type": "message"}
    return _item_fingerprint(body)


class AgencySession(SessionABC):
    """``agents.memory.Session`` bound to one ``(agent, sender_name)`` slice of the shared store."""

    def __init__(
        self,
        *,
        thread_manager: ThreadManager,
        agent: Agent,
        sender_name: str | None,
        agency_context: AgencyContext | None,
        agent_run_id: str | None,
        parent_run_id: str | None,
        run_trace_id: str | None,
        new_input_items: list[TResponseInputItem],
        sanitize_store_false: bool = False,
    ) -> None:
        self._thread_manager = thread_manager
        self._agent = agent
        self._sender_name = sender_name
        self._agency_context = agency_context
        self._agent_run_id = agent_run_id
        self._parent_run_id = parent_run_id
        self._run_trace_id = run_trace_id
        self._new_input_items = list(new_input_items)
        self._sanitize_store_false = sanitize_store_false
        self._current_agent_name = agent.name
        self._normalize_seq: dict[str, int] = {}
        self._model_new_items: list[TResponseInputItem] | None = None
        # The SDK fingerprints session items for retry rewinds; our store normalizes
        # ids, so matching must ignore them (see session_persistence._ignore_ids_for_matching).
        self._ignore_ids_for_matching = True
        # Identities of the raw input objects persisted at construction: that write
        # must bypass the suppression counters below (it *is* the write they guard).
        self._own_input_ids: set[int] = {id(item) for item in self._new_input_items}
        # Per-session, sequence-bounded reconciliation — never a store scan. The SDK
        # only passes genuinely new items to add_items (it tracks
        # _current_turn_persisted_item_count), so the only copies suppressed are:
        # - _new_input_fps: the new input already persisted at construction, which
        #   the SDK re-passes as normalized callback-output copies (bounded by the
        #   number of input items — identical model output is never suppressed);
        # - _stream_written_fps: items the per-event writer already claimed this
        #   run (consumed one-for-one);
        # - _session_written_fps: items this session stored (consumed one-for-one
        #   by stream-writer claims when a turn-end save races the event queue).
        self._new_input_fps: Counter[str] = Counter()
        for raw_item in self._new_input_items:
            key = _canonical_fingerprint(raw_item)
            if key is not None:
                self._new_input_fps[key] += 1
        self._stream_written_fps: Counter[str] = Counter()
        self._session_written_fps: Counter[str] = Counter()
        # New input is persisted up front (legacy prepare-time semantics). While
        # it is still pending as this run's fresh input it is excluded from the
        # history view so the model never sees it twice; the first session_input
        # callback consume clears the flag, after which it is plain history.
        self._pending_new_input = True
        self._new_input_stored_ids: set[int] = set()
        self.session_id = f"{agent.name}:{sender_name or 'user'}"

    # --- Session protocol -------------------------------------------------

    async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        history = self._history_for_model()
        if limit is None:
            return history
        # history[-0:] would slice from index 0 and return everything.
        return history[-limit:] if limit > 0 else []

    async def add_items(self, items: list[TResponseInputItem]) -> None:
        self.persist_items(items)

    async def pop_item(self) -> TResponseInputItem | None:
        popped = self._thread_manager.pop_message_for_pair(self._agent.name, self._sender_name)
        if popped is None:
            return None
        # Keep the write counters honest so a rewind/restore re-save of the same
        # item is not suppressed by the write that was just undone.
        fingerprint = _canonical_fingerprint(popped)
        if fingerprint is not None:
            if self._session_written_fps.get(fingerprint, 0) > 0:
                self._session_written_fps[fingerprint] -= 1
            elif self._stream_written_fps.get(fingerprint, 0) > 0:
                self._stream_written_fps[fingerprint] -= 1
        stripped = MessageFormatter.strip_agency_metadata([cast(dict[str, Any], popped)])
        return cast(TResponseInputItem, stripped[0])

    async def clear_session(self) -> None:
        self._thread_manager.remove_messages_for_pair(self._agent.name, self._sender_name)

    # --- Agency-facing helpers ---------------------------------------------

    @property
    def model_new_items(self) -> list[TResponseInputItem]:
        """Sanitized view of this run's new input items (what the model should see)."""
        if self._model_new_items is None:
            self._model_new_items = self._compute_model_new_items()
        return self._model_new_items

    def prepared_input(self) -> list[TResponseInputItem]:
        """Full model input for this run: sanitized history plus new items."""
        return self._history_for_model() + self.model_new_items

    def current_history_for_model(self) -> list[TResponseInputItem]:
        """Live conversation slice sanitized for the model (no new items appended)."""
        return self._history_for_model()

    def raw_history_count(self) -> int:
        """Stored item count for this slice — cheap, for logging (no sanitization).

        Excludes the still-pending new input so the number matches the model's
        history view; once the first callback consumes it, it counts as history.
        """
        count = len(self._thread_manager.get_conversation_history(self._agent.name, self._sender_name))
        if self._pending_new_input:
            count -= len(self._new_input_stored_ids)
        return count

    def session_input_callback(self, user_callback: SessionInputCallback | None = None) -> SessionInputCallback:
        """Build the RunConfig ``session_input_callback`` for this run.

        History arrives already sanitized via ``get_items``; the callback appends
        the sanitized new-input view so the model sees exactly the items Agency
        semantics require. A caller-provided callback composes after ours.
        """

        def _merge(
            history: list[TResponseInputItem], new_items: list[TResponseInputItem]
        ) -> list[TResponseInputItem] | Awaitable[list[TResponseInputItem]]:
            try:
                effective_new = self.model_new_items if new_items else []
                if user_callback is not None:
                    return user_callback(list(history), effective_new)
                return list(history) + effective_new
            finally:
                # After the first prepare cycle the persisted input becomes plain
                # history, so retries and rewinds see the honest store.
                self._pending_new_input = False

        return _merge

    def claim_streamed_item(self, item: TResponseInputItem) -> bool:
        """Decide whether the per-event stream writer should persist ``item`` itself.

        Returns False when this session already stored an equivalent item this run,
        consuming that recorded write one-for-one; otherwise records the pending
        stream write so a later ``persist_items`` call for the same turn item skips
        it. Both directions are matched only against this session's own counters,
        so identical items written by other slices or earlier runs never suppress.
        """
        fingerprint = _canonical_fingerprint(item)
        if fingerprint is not None and self._session_written_fps.get(fingerprint, 0) > 0:
            self._session_written_fps[fingerprint] -= 1
            return False
        if fingerprint is not None:
            self._stream_written_fps[fingerprint] += 1
        return True

    def persist_new_input(self) -> None:
        """Persist this run's new input immediately, like the legacy prepare step.

        Called once by ``create_agency_session`` so the store reflects the turn
        input even when the SDK run is mocked, short-circuits, or replays a
        cached conversation starter.
        """
        stored = self.persist_items(self._new_input_items)
        self._new_input_stored_ids.update(id(message) for message in stored)

    def persist_items(self, items: list[TResponseInputItem]) -> list[TResponseInputItem]:
        """Store items with agency metadata.

        Reconciliation is per-session and sequence-bounded rather than a store
        scan: the SDK never re-passes items it already saved, so suppression only
        applies to (a) the new input persisted at construction when the SDK
        re-passes its normalized copies, and (b) items the per-event stream
        writer already claimed this run — each consumed one-for-one. Identical
        items that are genuinely new (another turn, another slice, another run)
        always persist.

        Returns the list of stored message dicts.
        """
        to_store: list[TResponseInputItem] = []
        for item in items:
            fingerprint = _canonical_fingerprint(item)
            is_own_input = id(item) in self._own_input_ids
            if fingerprint is not None and not is_own_input:
                if self._new_input_fps.get(fingerprint, 0) > 0:
                    self._new_input_fps[fingerprint] -= 1
                    continue
                if self._stream_written_fps.get(fingerprint, 0) > 0:
                    self._stream_written_fps[fingerprint] -= 1
                    continue
            # The SDK may persist the model-facing form of items; the stored copy
            # always drops ephemeral content parts entirely.
            save_item = MessageFormatter.strip_ephemeral_content(item, drop_parts=True)
            if save_item is None or (isinstance(save_item, dict) and MessageFilter.should_filter(save_item)):
                continue
            # The construction write is already covered by _new_input_fps; only
            # later writes register as coverage for stream-writer claims, so an
            # assistant item echoing the user's input text is never suppressed.
            if fingerprint is not None and not is_own_input:
                self._session_written_fps[fingerprint] += 1
            enriched = MessageFormatter.add_agency_metadata(
                save_item,
                agent=self._current_agent_name,
                caller_agent=self._sender_name,
                agent_run_id=self._agent_run_id,
                parent_run_id=self._parent_run_id,
                run_trace_id=self._run_trace_id,
                history_protocol=MessageFormatter.resolve_history_protocol_for_agent_name(
                    self._current_agent_name,
                    default_agent=self._agent,
                    agency_context=self._agency_context,
                ),
            )
            citations = extract_file_citations_from_input_item(cast(dict[str, Any], save_item))
            if citations:
                enriched["citations"] = citations  # type: ignore[typeddict-unknown-key]
            to_store.append(enriched)
            handoff_target = self._handoff_target(save_item)
            if handoff_target is not None:
                self._current_agent_name = handoff_target

        normalized = StreamIdNormalizer().normalize_message_dicts(to_store, seq_by_agent_run_id=self._normalize_seq)
        if normalized:
            self._thread_manager.add_messages(normalized)
        return normalized

    # --- Internals ----------------------------------------------------------

    def _history_for_model(self) -> list[TResponseInputItem]:
        combined = self._sanitize_for_model(self._tagged_items())
        return [self._untag(item) for item in combined if item.get(_HISTORY_TAG) == "h"]

    def _compute_model_new_items(self) -> list[TResponseInputItem]:
        combined = self._sanitize_for_model(self._tagged_items())
        return [self._untag(item) for item in combined if item.get(_HISTORY_TAG) == "n"]

    def _tagged_items(self) -> list[dict[str, Any]]:
        """Slice history plus new input, tagged so sanitizers see one sequence."""
        history_items = self._thread_manager.get_conversation_history(self._agent.name, self._sender_name)
        if self._pending_new_input and self._new_input_stored_ids:
            # The just-persisted new input is supplied separately as "n" items;
            # skip its stored copies so the model sees it exactly once.
            history_items = [message for message in history_items if id(message) not in self._new_input_stored_ids]
        tagged = [
            dict(item, **{_HISTORY_TAG: "h"})  # type: ignore[typeddict-item]
            for item in history_items
        ]
        for item in self._new_input_items:
            # Enrich first so the model view matches legacy output exactly: the
            # sanitizer strips the metadata but keeps added fields like type.
            enriched = MessageFormatter.add_agency_metadata(
                item,
                agent=self._agent.name,
                caller_agent=self._sender_name,
                agent_run_id=self._agent_run_id,
                parent_run_id=self._parent_run_id,
                run_trace_id=self._run_trace_id,
                history_protocol=MessageFormatter.resolve_history_protocol(self._agent),
            )
            model_item = MessageFormatter.strip_ephemeral_content(enriched, drop_parts=False)
            if model_item is not None:
                tagged.append(dict(model_item, **{_HISTORY_TAG: "n"}))  # type: ignore[typeddict-item]
        return tagged

    def _sanitize_for_model(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        history = MessageFormatter.sanitize_tool_calls_in_history(items)
        history = MessageFormatter.ensure_tool_calls_content_safety(history)
        history = MessageFormatter.strip_agency_metadata(history)
        history = MessageFormatter.sanitize_replayed_tool_item_ids(history)
        if self._sanitize_store_false:
            history = sanitize_store_false_responses_input(history)
        return history

    @staticmethod
    def _untag(item: dict[str, Any]) -> TResponseInputItem:
        item.pop(_HISTORY_TAG, None)
        return cast(TResponseInputItem, item)

    def _handoff_target(self, item: TResponseInputItem) -> str | None:
        """Detect a completed handoff in a serialized output item.

        The SDK writes ``{"assistant": "<name>"}`` JSON as the handoff tool's
        function_call_output; the name is only trusted when it matches a known
        agency agent so arbitrary tool outputs cannot flip attribution.
        """
        if item.get("type") != "function_call_output":
            return None
        output = item.get("output")
        parsed: Any = None
        if isinstance(output, str):
            try:
                parsed = json.loads(output)
            except ValueError:
                return None
        elif isinstance(output, dict):
            parsed = output
        if not isinstance(parsed, dict):
            return None
        name = parsed.get("assistant")
        if not isinstance(name, str) or not name.strip():
            return None
        name = name.strip()
        agency_instance = getattr(self._agency_context, "agency_instance", None) if self._agency_context else None
        agents = getattr(agency_instance, "agents", None)
        # Without a roster to validate against (standalone agent use) there is no
        # legitimate handoff target — never trust the raw tool output.
        if not isinstance(agents, dict) or name not in agents:
            return None
        return name


def create_agency_session(
    *,
    agent: Agent,
    sender_name: str | None,
    agency_context: AgencyContext | None,
    new_input_items: list[TResponseInputItem],
    agent_run_id: str | None,
    parent_run_id: str | None,
    run_trace_id: str | None,
    run_config_override: RunConfig | None,
) -> AgencySession:
    """Validate stored-history compatibility and build the session for one run."""
    if not agency_context or not agency_context.thread_manager:
        raise RuntimeError(f"Agent '{agent.name}' missing ThreadManager in agency context.")

    thread_manager = agency_context.thread_manager
    compatibility_history = thread_manager.get_conversation_history(agent.name, sender_name) + [
        item for item in new_input_items if isinstance(item, dict)
    ]
    MessageFormatter.ensure_history_protocol_compatibility(
        compatibility_history,
        expected_protocol=MessageFormatter.resolve_history_protocol(agent),
        agent_name=agent.name,
    )
    sanitize_store_false = MessageFormatter.ensure_store_false_replay_settings(agent, run_config_override)

    session = AgencySession(
        thread_manager=thread_manager,
        agent=agent,
        sender_name=sender_name,
        agency_context=agency_context,
        agent_run_id=agent_run_id,
        parent_run_id=parent_run_id,
        run_trace_id=run_trace_id,
        new_input_items=new_input_items,
        sanitize_store_false=sanitize_store_false,
    )
    session.persist_new_input()
    return session

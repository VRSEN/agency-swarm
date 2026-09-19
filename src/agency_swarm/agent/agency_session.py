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
- ``persist_items`` dedupes against items appended since session creation, so
  the per-stream-event writer (``execution_stream_persistence``) and the SDK's
  own session saves never double-store the same item.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, deque
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
        self._baseline_count = len(thread_manager.get_all_messages())
        self._current_agent_name = agent.name
        self._normalize_seq: dict[str, int] = {}
        self._model_new_items: list[TResponseInputItem] | None = None
        # The SDK fingerprints session items for retry rewinds; our store normalizes
        # ids, so matching must ignore them (see session_persistence._ignore_ids_for_matching).
        self._ignore_ids_for_matching = True
        # Map from the model-facing form of each new-input item back to its raw
        # form. The SDK persists whatever the session_input_callback returned, i.e.
        # items whose ephemeral markers were already stripped for the model; the raw
        # form is needed so persist_items can drop the marked parts before storing.
        self._raw_input_by_key: dict[str, deque[TResponseInputItem]] = {}
        for raw_item in self._new_input_items:
            key = _canonical_fingerprint(raw_item)
            if key is not None:
                self._raw_input_by_key.setdefault(key, deque()).append(raw_item)
        # Model-form fingerprints of items already stored this run, so repeated
        # SDK saves (e.g. input re-persisted on a guardrail trip) dedupe against
        # the stored save-form even when the two differ by ephemeral parts.
        self._persisted_model_fps: Counter[str] = Counter()
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
        if limit is not None:
            return history[-limit:]
        return history

    async def add_items(self, items: list[TResponseInputItem]) -> None:
        self.persist_items(items)

    async def pop_item(self) -> TResponseInputItem | None:
        popped = self._thread_manager.pop_message_for_pair(self._agent.name, self._sender_name)
        if popped is None:
            return None
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

    def is_already_persisted(self, item: TResponseInputItem) -> bool:
        """True when an equal item already sits in the store tail appended since creation.

        Used by the per-stream-event writer so it does not double-store an item the
        SDK already saved through the session (or vice versa). Equality is the
        model-form fingerprint: agency metadata and volatile ids are ignored.
        """
        fingerprint = _canonical_fingerprint(item)
        if fingerprint is None:
            return False
        messages = self._thread_manager.get_all_messages()
        tail = messages[self._baseline_count :] if self._baseline_count <= len(messages) else []
        return any(_canonical_fingerprint(message) == fingerprint for message in tail)

    def persist_new_input(self) -> None:
        """Persist this run's new input immediately, like the legacy prepare step.

        Called once by ``create_agency_session`` so the store reflects the turn
        input even when the SDK run is mocked, short-circuits, or replays a
        cached conversation starter.
        """
        stored = self.persist_items(self._new_input_items)
        self._new_input_stored_ids.update(id(message) for message in stored)

    def persist_items(self, items: list[TResponseInputItem]) -> list[TResponseInputItem]:
        """Store items with agency metadata, skipping anything already persisted.

        Dedupe is scoped to messages appended since session construction so the
        SDK's saves and the per-stream-event writer cannot double-store items,
        while repeated-but-distinct earlier history never blocks a write.

        Returns the list of stored message dicts.
        """
        dedupe = self._tail_fingerprints()
        dedupe.update(self._persisted_model_fps)
        to_store: list[TResponseInputItem] = []
        for item in items:
            fingerprint = _canonical_fingerprint(item)
            if fingerprint is not None and dedupe.get(fingerprint, 0) > 0:
                dedupe[fingerprint] -= 1
                continue
            # The SDK persists the model-facing form of new input; swap back to
            # the raw item so ephemeral parts are dropped before storing.
            source = item
            if fingerprint is not None:
                raw_queue = self._raw_input_by_key.get(fingerprint)
                if raw_queue:
                    source = raw_queue.popleft()
            save_item = MessageFormatter.strip_ephemeral_content(source, drop_parts=True)
            if save_item is None or (isinstance(save_item, dict) and MessageFilter.should_filter(save_item)):
                continue
            if fingerprint is not None:
                self._persisted_model_fps[fingerprint] += 1
                dedupe[fingerprint] += 1
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

    def _tail_fingerprints(self) -> Counter[str]:
        messages = self._thread_manager.get_all_messages()
        tail = messages[self._baseline_count :] if self._baseline_count <= len(messages) else []
        counts: Counter[str] = Counter()
        for message in tail:
            fingerprint = _canonical_fingerprint(message)
            if fingerprint is not None:
                counts[fingerprint] += 1
        return counts

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
        if isinstance(agents, dict) and agents and name not in agents:
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

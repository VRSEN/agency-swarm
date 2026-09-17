"""Per-loop request coordination state and agency request leases."""

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from weakref import ReferenceType, ref

from agency_swarm import Agency
from agency_swarm.integrations.fastapi_utils import endpoint_handlers

# Keep the pre-split logger name so log records are unchanged.
logger = logging.getLogger("agency_swarm.integrations.fastapi_utils.endpoint_handlers")


@dataclass
class _AgencyRequestState:
    """Per-agency request coordination state for one event loop."""

    state_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    active_regular_requests: int = 0
    override_active: bool = False
    pending_overrides: int = 0
    state_changed: asyncio.Condition = field(init=False)

    def __post_init__(self) -> None:
        self.state_changed = asyncio.Condition(self.state_lock)


@dataclass
class _AgencyRequestLease:
    states: tuple[_AgencyRequestState, ...]
    is_override: bool


type _RequestStateEntry = tuple[ReferenceType[object], dict[asyncio.AbstractEventLoop, _AgencyRequestState]]
_AGENT_REQUEST_STATES: dict[int, _RequestStateEntry] = {}
_AGENCY_REQUEST_STATES_GUARD = threading.RLock()


def _remove_request_state_entry(subject_id: int, subject_ref: ReferenceType[object]) -> None:
    with endpoint_handlers._AGENCY_REQUEST_STATES_GUARD:
        existing = endpoint_handlers._AGENT_REQUEST_STATES.get(subject_id)
        if existing is not None and existing[0] is subject_ref:
            endpoint_handlers._AGENT_REQUEST_STATES.pop(subject_id, None)


def _get_identity_request_state(subject: object, loop: asyncio.AbstractEventLoop) -> _AgencyRequestState:
    """Return request coordination state for one object identity and event loop."""
    subject_id = id(subject)
    with endpoint_handlers._AGENCY_REQUEST_STATES_GUARD:
        entry = endpoint_handlers._AGENT_REQUEST_STATES.get(subject_id)
        if entry is None or entry[0]() is not subject:
            per_loop: dict[asyncio.AbstractEventLoop, _AgencyRequestState] = {}

            def remove_expired_subject(expired_ref: ReferenceType[object]) -> None:
                _remove_request_state_entry(subject_id, expired_ref)

            subject_ref = ref(subject, remove_expired_subject)
            endpoint_handlers._AGENT_REQUEST_STATES[subject_id] = (subject_ref, per_loop)
        else:
            per_loop = entry[1]

        # Drop closed-loop state to avoid unbounded growth in long-lived processes.
        closed_loops = [existing_loop for existing_loop in per_loop if existing_loop.is_closed()]
        for closed_loop in closed_loops:
            per_loop.pop(closed_loop, None)

        active_loops = [existing_loop for existing_loop in per_loop if not existing_loop.is_closed()]
        if active_loops and loop not in per_loop:
            logger.warning(
                "Agent '%s' is being reused across event loops; request coordination remains per-loop only.",
                getattr(subject, "name", subject.__class__.__name__),
            )

        existing = per_loop.get(loop)
        if existing is not None:
            return existing

        created = _AgencyRequestState()
        per_loop[loop] = created
        return created


async def _get_agency_request_states(agency: Agency) -> tuple[_AgencyRequestState, ...]:
    """Return states for every unique underlying agent in deterministic order."""
    loop = asyncio.get_running_loop()
    agents_map = getattr(agency, "agents", None)
    subjects = list(agents_map.values()) if isinstance(agents_map, dict) and agents_map else [agency]
    unique_subjects = {id(subject): subject for subject in subjects}
    return tuple(
        _get_identity_request_state(unique_subjects[subject_id], loop) for subject_id in sorted(unique_subjects)
    )


async def _acquire_request_state(state: _AgencyRequestState, is_override: bool) -> None:
    async with state.state_changed:
        if is_override:
            state.pending_overrides += 1
            try:
                await state.state_changed.wait_for(
                    lambda: not state.override_active and state.active_regular_requests == 0
                )
                state.override_active = True
            finally:
                state.pending_overrides -= 1
                state.state_changed.notify_all()
        else:
            await state.state_changed.wait_for(lambda: not state.override_active and state.pending_overrides == 0)
            state.active_regular_requests += 1


async def _release_request_state(state: _AgencyRequestState, is_override: bool) -> None:
    async with state.state_changed:
        if is_override:
            state.override_active = False
        else:
            state.active_regular_requests -= 1
        state.state_changed.notify_all()


async def _acquire_agency_request_lease(agency: Agency, is_override: bool) -> _AgencyRequestLease:
    """Acquire reader or writer leases for every shared underlying agent."""
    states = await endpoint_handlers._get_agency_request_states(agency)
    acquired: list[_AgencyRequestState] = []
    try:
        for state in states:
            await _acquire_request_state(state, is_override)
            acquired.append(state)
    except BaseException:
        for state in reversed(acquired):
            await endpoint_handlers._release_request_state(state, is_override)
        raise
    return _AgencyRequestLease(states=tuple(acquired), is_override=is_override)


async def _release_agency_request_lease(lease: _AgencyRequestLease) -> None:
    """Release a previously acquired request lease."""
    while lease.states:
        state = lease.states[-1]
        await endpoint_handlers._release_request_state(state, lease.is_override)
        lease.states = lease.states[:-1]

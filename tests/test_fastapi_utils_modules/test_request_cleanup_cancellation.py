"""Request cleanup must finish before cancellation frees its caller."""

import asyncio

import pytest

from agency_swarm import Agency, Agent
from agency_swarm.integrations.fastapi_utils import endpoint_handlers
from agency_swarm.integrations.fastapi_utils.override_policy import RequestOverridePolicy
from agency_swarm.integrations.fastapi_utils.override_session import _RequestOverrideSession
from agency_swarm.integrations.fastapi_utils.request_state import _AgencyRequestLease, _get_agency_request_states


async def test_repeated_cancellation_waits_for_lease_release(monkeypatch: pytest.MonkeyPatch) -> None:
    agency = Agency(Agent(name="Cleanup", instructions="No model calls"))
    session = _RequestOverrideSession(agency, RequestOverridePolicy(None))
    await session.acquire()
    entered = asyncio.Event()
    release = asyncio.Event()
    original = endpoint_handlers._release_agency_request_lease

    async def blocked(lease: _AgencyRequestLease) -> None:
        entered.set()
        await release.wait()
        await original(lease)

    monkeypatch.setattr(endpoint_handlers, "_release_agency_request_lease", blocked)
    cleanup = asyncio.create_task(session.cleanup())
    await entered.wait()
    cleanup.cancel()
    cleanup.cancel()
    # Check cancellation while release is still blocked, without timeout races.
    marker = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_later(0, marker.set_result, None)
    await marker
    returned_before_release = cleanup.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await cleanup

    assert not returned_before_release
    assert session.lease is None


async def test_concurrent_failed_release_can_be_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    agency = Agency(Agent(name="Cleanup", instructions="No model calls"))
    session = _RequestOverrideSession(agency, RequestOverridePolicy(None))
    await session.acquire()
    entered = asyncio.Event()
    fail = asyncio.Event()
    original = endpoint_handlers._release_agency_request_lease

    async def blocked(_lease: _AgencyRequestLease) -> None:
        entered.set()
        await fail.wait()
        raise RuntimeError("release failed")

    monkeypatch.setattr(endpoint_handlers, "_release_agency_request_lease", blocked)
    first = asyncio.create_task(session.cleanup())
    await entered.wait()
    second = asyncio.create_task(session.cleanup())
    marker = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_later(0, marker.set_result, None)
    await marker
    fail.set()
    outcomes = await asyncio.gather(first, second, return_exceptions=True)

    assert all(isinstance(outcome, RuntimeError) and str(outcome) == "release failed" for outcome in outcomes)
    monkeypatch.setattr(endpoint_handlers, "_release_agency_request_lease", original)
    await session.cleanup()
    assert session.lease is None
    assert all(state.active_regular_requests == 0 for state in await _get_agency_request_states(agency))


async def test_concurrent_cleanup_callers_wait_for_same_release(monkeypatch: pytest.MonkeyPatch) -> None:
    agency = Agency(Agent(name="Cleanup", instructions="No model calls"))
    session = _RequestOverrideSession(agency, RequestOverridePolicy(None))
    await session.acquire()
    entered = asyncio.Event()
    release = asyncio.Event()
    original = endpoint_handlers._release_agency_request_lease
    calls = 0

    async def blocked(lease: _AgencyRequestLease) -> None:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        await original(lease)

    monkeypatch.setattr(endpoint_handlers, "_release_agency_request_lease", blocked)
    first = asyncio.create_task(session.cleanup())
    await entered.wait()
    second = asyncio.create_task(session.cleanup())
    marker = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_later(0, marker.set_result, None)
    await marker
    completed_early = second.done()
    release.set()
    await asyncio.gather(first, second)

    assert not completed_early
    assert calls == 1
    assert session.lease is None

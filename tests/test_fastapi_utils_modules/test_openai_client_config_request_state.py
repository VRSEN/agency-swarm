"""Minimal tests for FastAPI request models that include `client_config`.

The end-to-end behavior is covered in integration tests under `tests/integration/fastapi/`.
"""

import asyncio
import gc
from weakref import WeakKeyDictionary

import pytest


@pytest.mark.asyncio
async def test_make_response_endpoint_builds_upload_client_after_lease(monkeypatch) -> None:
    """Upload client derivation must happen only after the request lease is acquired."""
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    lease_acquired = False
    upload_client = object()

    class _ThreadManager:
        def get_all_messages(self):
            return []

    class _Response:
        def __init__(self, final_output):
            self.final_output = final_output

    class _AgentState:
        def __init__(self):
            self.model = "gpt-4o-mini"
            self.model_settings = None

    class _Agency:
        def __init__(self):
            self.agents = {"A": _AgentState()}
            self.thread_manager = _ThreadManager()

        async def get_response(self, **_kwargs):
            return _Response("ok")

    agency = _Agency()

    def _agency_factory(**_kwargs):
        return agency

    async def _attach_noop(_agency):
        return None

    async def _acquire(_agency, is_override: bool):
        nonlocal lease_acquired
        assert is_override is True
        lease_acquired = True
        return object()

    async def _release(_lease):
        return None

    def _build_upload_client(_agency, _config, recipient_agent: str | None = None):
        assert recipient_agent is None
        assert lease_acquired is True
        return upload_client

    async def _fake_upload_from_urls(_file_urls, allowed_local_dirs=None, openai_client=None):
        del allowed_local_dirs
        assert openai_client is upload_client
        return {"doc.txt": "file-123"}

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)
    monkeypatch.setattr(endpoint_handlers, "apply_openai_client_config", lambda _agency, _config: None)
    monkeypatch.setattr(endpoint_handlers, "_acquire_agency_request_lease", _acquire)
    monkeypatch.setattr(endpoint_handlers, "_release_agency_request_lease", _release)
    monkeypatch.setattr(endpoint_handlers, "_build_file_upload_client", _build_upload_client)
    monkeypatch.setattr(endpoint_handlers, "upload_from_urls", _fake_upload_from_urls)

    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)
    response = await handler(
        BaseRequest(
            message="hello",
            file_urls={"doc.txt": "https://example.com/doc.txt"},
            client_config=ClientConfig(default_headers={"x-request-id": "req-1"}),
        ),
        token=None,
    )

    assert response["response"] == "ok"
    assert response["file_ids_map"] == {"doc.txt": "file-123"}


@pytest.mark.asyncio
async def test_make_response_endpoint_serializes_singleton_agency_requests(monkeypatch) -> None:
    """Concurrent requests against a cached agency should be serialized by the handler."""
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    class _ThreadManager:
        def get_all_messages(self):
            return []

    class _Response:
        def __init__(self, final_output):
            self.final_output = final_output

    class _AgentState:
        def __init__(self):
            self.model = "gpt-4o-mini"
            self.model_settings = None

    class _Agency:
        def __init__(self):
            self.agents = {"A": _AgentState()}
            self.thread_manager = _ThreadManager()
            self._in_flight = 0
            self.max_in_flight = 0

        async def get_response(self, **_kwargs):
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
            await asyncio.sleep(0.05)
            self._in_flight -= 1
            return _Response("ok")

    agency = _Agency()

    def _agency_factory(**_kwargs):
        return agency

    async def _attach_noop(_agency):
        return None

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)
    monkeypatch.setattr(endpoint_handlers, "apply_openai_client_config", lambda _agency, _config: None)

    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)

    request_a = BaseRequest(message="a", client_config=ClientConfig(default_headers={"x-request": "a"}))
    # No client_config on the second request to verify mixed traffic is still serialized.
    request_b = BaseRequest(message="b")

    await asyncio.gather(handler(request_a, token=None), handler(request_b, token=None))

    assert agency.max_in_flight == 1


@pytest.mark.asyncio
async def test_make_response_endpoint_allows_concurrency_without_client_config(monkeypatch) -> None:
    """Requests without client overrides should not be serialized."""
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest

    class _ThreadManager:
        def get_all_messages(self):
            return []

    class _Response:
        def __init__(self, final_output):
            self.final_output = final_output

    class _AgentState:
        def __init__(self):
            self.model = "gpt-4o-mini"
            self.model_settings = None

    class _Agency:
        def __init__(self):
            self.agents = {"A": _AgentState()}
            self.thread_manager = _ThreadManager()
            self._in_flight = 0
            self.max_in_flight = 0

        async def get_response(self, **_kwargs):
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
            await asyncio.sleep(0.05)
            self._in_flight -= 1
            return _Response("ok")

    agency = _Agency()

    def _agency_factory(**_kwargs):
        return agency

    async def _attach_noop(_agency):
        return None

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)

    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)
    request_a = BaseRequest(message="a")
    request_b = BaseRequest(message="b")

    await asyncio.gather(handler(request_a, token=None), handler(request_b, token=None))

    assert agency.max_in_flight == 2


@pytest.mark.asyncio
async def test_make_response_endpoint_does_not_release_unacquired_lock(monkeypatch) -> None:
    """Lock acquisition failures should not trigger an invalid release call."""
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    class _ThreadManager:
        def get_all_messages(self):
            return []

    class _AgentState:
        def __init__(self):
            self.model = "gpt-4o-mini"
            self.model_settings = None

    class _Agency:
        def __init__(self):
            self.agents = {"A": _AgentState()}
            self.thread_manager = _ThreadManager()

        async def get_response(self, **_kwargs):
            return None

    agency = _Agency()
    released = False

    def _agency_factory(**_kwargs):
        return agency

    async def _attach_noop(_agency):
        return None

    async def _fail_acquire(_agency, is_override: bool):
        assert is_override is True
        raise RuntimeError("acquire failed")

    async def _release_lease(_lease):
        nonlocal released
        released = True

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)
    monkeypatch.setattr(endpoint_handlers, "_acquire_agency_request_lease", _fail_acquire)
    monkeypatch.setattr(endpoint_handlers, "_release_agency_request_lease", _release_lease)

    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)
    request = BaseRequest(message="a", client_config=ClientConfig(default_headers={"x-request": "a"}))

    with pytest.raises(RuntimeError, match="acquire failed"):
        await handler(request, token=None)

    assert released is False


@pytest.mark.asyncio
async def test_cancelled_override_notifies_waiting_regular_requests(monkeypatch) -> None:
    """Cancelling a waiting override should wake regular requests blocked on pending_overrides."""
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers

    class _ManualCondition:
        def __init__(self, lock: asyncio.Lock):
            self._lock = lock
            self._event = asyncio.Event()

        async def __aenter__(self):
            await self._lock.acquire()
            return self

        async def __aexit__(self, exc_type, exc, tb):
            self._lock.release()

        async def wait_for(self, predicate):
            while not predicate():
                self._lock.release()
                try:
                    await self._event.wait()
                finally:
                    await self._lock.acquire()
                    self._event.clear()
            return True

        def notify_all(self):
            self._event.set()

    class _Agency:
        pass

    state = endpoint_handlers._AgencyRequestState()
    state.active_regular_requests = 1
    state.override_active = False
    state.pending_overrides = 0
    state.state_changed = _ManualCondition(state.state_lock)

    async def _get_state(_agency):
        return state

    monkeypatch.setattr(endpoint_handlers, "_get_agency_request_state", _get_state)

    agency = _Agency()

    async def _wait_until(predicate):
        while not predicate():
            await asyncio.sleep(0)

    override_task = asyncio.create_task(endpoint_handlers._acquire_agency_request_lease(agency, is_override=True))
    await asyncio.wait_for(_wait_until(lambda: state.pending_overrides == 1), timeout=0.2)
    assert state.pending_overrides == 1

    regular_task = asyncio.create_task(endpoint_handlers._acquire_agency_request_lease(agency, is_override=False))
    await asyncio.sleep(0)
    assert regular_task.done() is False

    override_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await override_task

    regular_lease = await asyncio.wait_for(regular_task, timeout=0.2)
    await endpoint_handlers._release_agency_request_lease(regular_lease)


@pytest.mark.asyncio
async def test_get_agency_request_state_isolated_per_event_loop(monkeypatch) -> None:
    """Cross-loop agency reuse should create independent per-loop coordination state."""
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers

    class _Agency:
        pass

    class _Loop:
        def __init__(self, closed: bool = False):
            self._closed = closed

        def is_closed(self) -> bool:
            return self._closed

    agency = _Agency()
    loop_a = _Loop()
    loop_b = _Loop()

    monkeypatch.setattr(endpoint_handlers, "_AGENCY_REQUEST_STATES", WeakKeyDictionary())
    monkeypatch.setattr(endpoint_handlers.asyncio, "get_running_loop", lambda: loop_a)
    state_a = await endpoint_handlers._get_agency_request_state(agency)
    state_a_again = await endpoint_handlers._get_agency_request_state(agency)
    assert state_a is state_a_again

    monkeypatch.setattr(endpoint_handlers.asyncio, "get_running_loop", lambda: loop_b)
    state_b = await endpoint_handlers._get_agency_request_state(agency)
    assert state_b is not state_a


@pytest.mark.asyncio
async def test_get_agency_request_state_prunes_closed_loop_entries(monkeypatch) -> None:
    """Closed event-loop entries should be removed during state lookup."""
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers

    class _Agency:
        pass

    class _Loop:
        def __init__(self, closed: bool = False):
            self._closed = closed

        def is_closed(self) -> bool:
            return self._closed

    agency = _Agency()
    closed_loop = _Loop(closed=False)
    active_loop = _Loop(closed=False)

    monkeypatch.setattr(endpoint_handlers, "_AGENCY_REQUEST_STATES", WeakKeyDictionary())
    monkeypatch.setattr(endpoint_handlers.asyncio, "get_running_loop", lambda: closed_loop)
    await endpoint_handlers._get_agency_request_state(agency)

    closed_loop._closed = True
    monkeypatch.setattr(endpoint_handlers.asyncio, "get_running_loop", lambda: active_loop)
    await endpoint_handlers._get_agency_request_state(agency)

    gc.collect()
    per_loop = endpoint_handlers._AGENCY_REQUEST_STATES[agency]
    assert len(per_loop) == 1
    assert active_loop in per_loop


@pytest.mark.asyncio
async def test_make_response_endpoint_blocks_new_regular_requests_while_override_waits(monkeypatch) -> None:
    """Pending override requests should block new regular requests to avoid starvation."""
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    class _ThreadManager:
        def get_all_messages(self):
            return []

    class _Response:
        def __init__(self, final_output):
            self.final_output = final_output

    class _AgentState:
        def __init__(self):
            self.model = "gpt-4o-mini"
            self.model_settings = None

    class _Agency:
        def __init__(self):
            self.agents = {"A": _AgentState()}
            self.thread_manager = _ThreadManager()
            self._in_flight = 0
            self.max_in_flight = 0
            self._calls = 0
            self.first_request_started = asyncio.Event()
            self.allow_first_request_to_finish = asyncio.Event()

        async def get_response(self, **_kwargs):
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
            self._calls += 1
            try:
                if self._calls == 1:
                    self.first_request_started.set()
                    await self.allow_first_request_to_finish.wait()
                return _Response("ok")
            finally:
                self._in_flight -= 1

    agency = _Agency()

    def _agency_factory(**_kwargs):
        return agency

    async def _attach_noop(_agency):
        return None

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)
    monkeypatch.setattr(endpoint_handlers, "apply_openai_client_config", lambda _agency, _config: None)

    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)
    request_regular_a = BaseRequest(message="a")
    request_override = BaseRequest(message="o", client_config=ClientConfig(default_headers={"x-request": "o"}))
    request_regular_b = BaseRequest(message="b")

    regular_a_task = asyncio.create_task(handler(request_regular_a, token=None))
    await asyncio.wait_for(agency.first_request_started.wait(), timeout=0.2)
    override_task = asyncio.create_task(handler(request_override, token=None))
    await asyncio.sleep(0)
    regular_b_task = asyncio.create_task(handler(request_regular_b, token=None))
    agency.allow_first_request_to_finish.set()

    await asyncio.gather(regular_a_task, override_task, regular_b_task)

    assert agency.max_in_flight == 1

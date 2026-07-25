"""Minimal tests for FastAPI request models that include `client_config`.

The end-to-end behavior is covered in integration tests under `tests/integration/fastapi/`.
"""

import asyncio

import pytest
from pydantic import ValidationError


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
async def test_make_response_endpoint_forwards_structured_message_without_file_upload(monkeypatch) -> None:
    """Structured message attachments should use the core message contract, not file_urls upload."""
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest

    structured_message = [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_image",
                    "image_url": "data:image/png;base64,AAAA",
                    "detail": "auto",
                },
                {"type": "input_text", "text": "Describe this image."},
            ],
        },
        {"role": "user", "content": "Describe this scene. How many trees do you see?"},
    ]
    seen_message = None

    class _ThreadManager:
        def get_all_messages(self):
            return []

    class _Response:
        final_output = "ok"

    class _Agency:
        def __init__(self):
            self.thread_manager = _ThreadManager()

        async def get_response(self, **kwargs):
            nonlocal seen_message
            seen_message = kwargs["message"]
            return _Response()

    async def _attach_noop(_agency):
        return None

    async def _unexpected_upload(*_args, **_kwargs):
        raise AssertionError("structured message input must not call file_urls upload")

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)
    monkeypatch.setattr(endpoint_handlers, "upload_from_urls", _unexpected_upload)

    handler = make_response_endpoint(BaseRequest, lambda **_: _Agency(), verify_token=lambda: None)
    response = await handler(BaseRequest(message=structured_message), token=None)

    assert response["response"] == "ok"
    assert seen_message == structured_message
    assert "file_ids_map" not in response


def test_base_request_rejects_invalid_structured_messages() -> None:
    """The public request model should reject non-object structured items."""
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest

    invalid_messages = [
        [],
        ["not an object"],
    ]

    for message in invalid_messages:
        with pytest.raises(ValidationError):
            BaseRequest.model_validate({"message": message})


def test_base_request_accepts_sdk_easy_input_message_string_content() -> None:
    """EasyInputMessageParam content may be plain text in current OpenAI SDK types."""
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest

    message = [{"role": "user", "content": "Describe this scene. How many trees do you see?"}]

    request = BaseRequest.model_validate({"message": message})

    assert request.message == message


def test_base_request_does_not_own_image_detail_literals() -> None:
    """The OpenAI SDK/API should own image detail literals, not the FastAPI shim."""
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest

    message = [
        {
            "role": "user",
            "content": [{"type": "input_image", "image_url": "data:image/png;base64,AAAA", "detail": "original"}],
        }
    ]

    request = BaseRequest.model_validate({"message": message})

    assert request.message == message


def test_base_request_message_schema_keeps_responses_items_pass_through() -> None:
    """Generated OpenAPI should avoid owning a partial Responses content schema."""
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest

    message_schema = BaseRequest.model_json_schema()["properties"]["message"]

    assert message_schema["anyOf"][0] == {"type": "string"}
    structured_schema = message_schema["anyOf"][1]
    assert structured_schema["minItems"] == 1
    assert structured_schema["items"] == {"type": "object", "additionalProperties": True}


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
async def test_cleanup_failure_restores_snapshots_and_releases_writer_lease(monkeypatch) -> None:
    """Cleanup failures must not leave the shared agent writer-locked."""
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.override_policy import RequestOverridePolicy

    class _Agent:
        pass

    class _Agency:
        agents = {"A": _Agent()}

    agency = _Agency()
    lease = await endpoint_handlers._acquire_agency_request_lease(agency, is_override=True)
    cleanup_calls: list[str] = []

    async def _fail_cleanup() -> None:
        cleanup_calls.append("cleanup")
        raise RuntimeError("primary cleanup failure")

    def _restore_hosted(_agency) -> None:
        cleanup_calls.append("hosted")

    def _fail_oauth_restore(_agency, _snapshot) -> None:
        cleanup_calls.append("oauth")
        raise ValueError("secondary OAuth restore failure")

    def _restore_client(_agency, _snapshot) -> None:
        cleanup_calls.append("client")

    monkeypatch.setattr(endpoint_handlers, "cleanup_oauth_runtime_mcp_servers", _fail_cleanup)
    monkeypatch.setattr(endpoint_handlers, "restore_hosted_mcp_oauth_tools", _restore_hosted)
    monkeypatch.setattr(endpoint_handlers, "_restore_oauth_agent_state", _fail_oauth_restore)
    monkeypatch.setattr(endpoint_handlers, "_restore_agency_state", _restore_client)

    session = endpoint_handlers._RequestOverrideSession(
        agency=agency,
        policy=RequestOverridePolicy(None),
        restore_oauth_state=True,
        lease=lease,
        oauth_snapshot={},
        restore_snapshot={},
    )

    with pytest.raises(RuntimeError, match="primary cleanup failure"):
        await session.cleanup()
    await session.cleanup()

    later_lease = await asyncio.wait_for(
        endpoint_handlers._acquire_agency_request_lease(agency, is_override=True),
        timeout=0.2,
    )
    await endpoint_handlers._release_agency_request_lease(later_lease)

    assert cleanup_calls == ["cleanup", "hosted", "oauth", "client"]


@pytest.mark.asyncio
async def test_cleanup_retries_only_unreleased_regular_states(monkeypatch) -> None:
    """Partial release retries must not decrement an already released reader twice."""
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.override_policy import RequestOverridePolicy

    class _Agency:
        pass

    agency = _Agency()
    state_a = endpoint_handlers._AgencyRequestState(active_regular_requests=1)
    state_b = endpoint_handlers._AgencyRequestState(active_regular_requests=1)
    lease = endpoint_handlers._AgencyRequestLease(states=(state_a, state_b), is_override=False)
    release_attempts: list[object] = []
    original_release = endpoint_handlers._release_request_state

    async def _fail_second_release(state, is_override: bool) -> None:
        release_attempts.append(state)
        if len(release_attempts) == 2:
            raise RuntimeError("second release failed")
        await original_release(state, is_override)

    async def _get_states(_agency):
        return (state_a, state_b)

    monkeypatch.setattr(endpoint_handlers, "_release_request_state", _fail_second_release)
    monkeypatch.setattr(endpoint_handlers, "_get_agency_request_states", _get_states)

    session = endpoint_handlers._RequestOverrideSession(
        agency=agency,
        policy=RequestOverridePolicy(None),
        lease=lease,
    )

    with pytest.raises(RuntimeError, match="second release failed"):
        await session.cleanup()

    assert lease.states == (state_a,)
    assert [state_a.active_regular_requests, state_b.active_regular_requests] == [1, 0]

    await session.cleanup()

    assert session.lease is None
    assert [state_a.active_regular_requests, state_b.active_regular_requests] == [0, 0]

    future_lease = await asyncio.wait_for(
        endpoint_handlers._acquire_agency_request_lease(agency, is_override=True),
        timeout=0.2,
    )
    await endpoint_handlers._release_agency_request_lease(future_lease)


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

    async def _get_states(_agency):
        return (state,)

    monkeypatch.setattr(endpoint_handlers, "_get_agency_request_states", _get_states)

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

    monkeypatch.setattr(endpoint_handlers, "_AGENT_REQUEST_STATES", {})
    state_a = endpoint_handlers._get_identity_request_state(agency, loop_a)
    state_a_again = endpoint_handlers._get_identity_request_state(agency, loop_a)
    assert state_a is state_a_again

    state_b = endpoint_handlers._get_identity_request_state(agency, loop_b)
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

    monkeypatch.setattr(endpoint_handlers, "_AGENT_REQUEST_STATES", {})
    endpoint_handlers._get_identity_request_state(agency, closed_loop)

    closed_loop._closed = True
    endpoint_handlers._get_identity_request_state(agency, active_loop)

    per_loop = endpoint_handlers._AGENT_REQUEST_STATES[id(agency)][1]
    assert len(per_loop) == 1
    assert active_loop in per_loop


@pytest.mark.asyncio
async def test_shared_agent_wrappers_serialize_writers_but_not_readers() -> None:
    from agency_swarm import Agency, Agent
    from agency_swarm.agency.helpers import build_fastapi_agencies
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers

    source = Agency(Agent(name="Shared", instructions="test"), name="shared")
    factory = build_fastapi_agencies(source)["shared"]
    agency_a = factory()
    agency_b = factory()
    assert agency_a.agents["Shared"] is agency_b.agents["Shared"]

    writer_a = await endpoint_handlers._acquire_agency_request_lease(agency_a, is_override=True)
    writer_b_task = asyncio.create_task(endpoint_handlers._acquire_agency_request_lease(agency_b, is_override=True))
    await asyncio.sleep(0)
    assert writer_b_task.done() is False
    await endpoint_handlers._release_agency_request_lease(writer_a)
    writer_b = await asyncio.wait_for(writer_b_task, timeout=0.2)
    await endpoint_handlers._release_agency_request_lease(writer_b)

    readers = await asyncio.gather(
        endpoint_handlers._acquire_agency_request_lease(agency_a, is_override=False),
        endpoint_handlers._acquire_agency_request_lease(agency_b, is_override=False),
    )
    for lease in readers:
        await endpoint_handlers._release_agency_request_lease(lease)


@pytest.mark.asyncio
async def test_overlapping_agents_serialize_while_disjoint_agents_continue() -> None:
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers

    class _Agent:
        pass

    class _Agency:
        def __init__(self, *agents: _Agent) -> None:
            self.agents = {str(index): agent for index, agent in enumerate(agents)}

    shared = _Agent()
    held_agency = _Agency(shared, _Agent())
    overlapping_agency = _Agency(shared, _Agent())
    disjoint_agency = _Agency(_Agent())

    held = await endpoint_handlers._acquire_agency_request_lease(held_agency, is_override=True)
    overlapping_task = asyncio.create_task(
        endpoint_handlers._acquire_agency_request_lease(overlapping_agency, is_override=True)
    )
    disjoint = await asyncio.wait_for(
        endpoint_handlers._acquire_agency_request_lease(disjoint_agency, is_override=True),
        timeout=0.2,
    )
    await asyncio.sleep(0)
    assert overlapping_task.done() is False

    await endpoint_handlers._release_agency_request_lease(disjoint)
    await endpoint_handlers._release_agency_request_lease(held)
    overlapping = await asyncio.wait_for(overlapping_task, timeout=0.2)
    await endpoint_handlers._release_agency_request_lease(overlapping)


@pytest.mark.asyncio
async def test_cancelled_multi_agent_acquisition_rolls_back_partial_writer() -> None:
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers

    class _Agent:
        pass

    class _Agency:
        def __init__(self, *agents: _Agent) -> None:
            self.agents = {str(index): agent for index, agent in enumerate(agents)}

    first, second = sorted((_Agent(), _Agent()), key=id)
    blocker = await endpoint_handlers._acquire_agency_request_lease(_Agency(second), is_override=True)
    combined = _Agency(first, second)
    states = await endpoint_handlers._get_agency_request_states(combined)
    waiting_task = asyncio.create_task(endpoint_handlers._acquire_agency_request_lease(combined, is_override=True))

    async def partial_writer_is_waiting() -> None:
        while not states[0].override_active or states[1].pending_overrides == 0:
            await asyncio.sleep(0)

    await asyncio.wait_for(partial_writer_is_waiting(), timeout=0.2)
    waiting_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting_task
    assert states[0].override_active is False

    await endpoint_handlers._release_agency_request_lease(blocker)
    reader = await endpoint_handlers._acquire_agency_request_lease(_Agency(first), is_override=False)
    await endpoint_handlers._release_agency_request_lease(reader)


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

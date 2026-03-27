"""Minimal tests for FastAPI request models that include `client_config`.

The end-to-end behavior is covered in integration tests under `tests/integration/fastapi/`.
"""

import pytest


@pytest.mark.asyncio
async def test_make_stream_endpoint_background_cleanup_without_stream_consumption(monkeypatch) -> None:
    """Cleanup should run from response background even if body iterator is never consumed."""
    pytest.importorskip("agents")

    from agency_swarm.agent.execution_stream_response import StreamingRunResponse
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import (
        ActiveRunRegistry,
        make_stream_endpoint,
    )
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    class _HttpRequest:
        async def is_disconnected(self) -> bool:
            return False

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

        def get_response_stream(self, **_kwargs):
            async def _stream():
                if False:
                    yield {}

            return StreamingRunResponse(_stream())

    agency = _Agency()
    released = 0
    restored = 0

    def _agency_factory(**_kwargs):
        return agency

    async def _attach_noop(_agency):
        return None

    async def _release_lease(_lease):
        nonlocal released
        released += 1

    def _restore_state(_agency, _snapshot):
        nonlocal restored
        restored += 1

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)
    monkeypatch.setattr(endpoint_handlers, "apply_openai_client_config", lambda _agency, _config: None)
    monkeypatch.setattr(endpoint_handlers, "_release_agency_request_lease", _release_lease)
    monkeypatch.setattr(endpoint_handlers, "_restore_agency_state", _restore_state)

    handler = make_stream_endpoint(
        BaseRequest,
        _agency_factory,
        verify_token=lambda: None,
        run_registry=ActiveRunRegistry(),
    )

    request = BaseRequest(message="a", client_config=ClientConfig(default_headers={"x-request": "a"}))
    response = await handler(http_request=_HttpRequest(), request=request, token=None)

    assert released == 0
    assert restored == 0
    assert response.background is not None

    await response.background()

    assert released == 1
    assert restored == 1

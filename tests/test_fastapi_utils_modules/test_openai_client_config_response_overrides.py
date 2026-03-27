"""Minimal tests for FastAPI request models that include `client_config`.

The end-to-end behavior is covered in integration tests under `tests/integration/fastapi/`.
"""

import pytest


@pytest.mark.asyncio
async def test_make_response_endpoint_applies_client_config_to_agent_client_sync(monkeypatch) -> None:
    """Request client_config should provide a sync OpenAI client for attachment lookups."""
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

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
            self._openai_client = None
            self._openai_client_sync = None

        @property
        def client_sync(self):
            from openai import OpenAI

            if self._openai_client_sync is None:
                self._openai_client_sync = OpenAI()
            return self._openai_client_sync

    class _Agency:
        def __init__(self):
            self.agents = {"A": _AgentState()}
            self.thread_manager = _ThreadManager()

        async def get_response(self, **_kwargs):
            # Simulate attachment manager behavior that relies on sync client.
            api_key = self.agents["A"].client_sync.api_key
            assert api_key == "sk-request-key"
            return _Response("ok")

    agency = _Agency()

    def _agency_factory(**_kwargs):
        return agency

    async def _attach_noop(_agency):
        return None

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)
    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)

    response = await handler(
        BaseRequest(
            message="hi",
            client_config=ClientConfig(api_key="sk-request-key", base_url="https://api.openai.com/v1"),
        ),
        token=None,
    )

    assert response["response"] == "ok"


@pytest.mark.asyncio
async def test_make_response_endpoint_restores_agent_client_sync_after_override(monkeypatch) -> None:
    """Sync OpenAI client override should be request-scoped and restored after the call."""
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-default")
    seen_api_keys: list[str | None] = []

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
            self._openai_client = None
            self._openai_client_sync = None

        @property
        def client_sync(self):
            from openai import OpenAI

            if self._openai_client_sync is None:
                self._openai_client_sync = OpenAI()
            return self._openai_client_sync

    class _Agency:
        def __init__(self):
            self.agents = {"A": _AgentState()}
            self.thread_manager = _ThreadManager()

        async def get_response(self, **_kwargs):
            seen_api_keys.append(self.agents["A"].client_sync.api_key)
            return _Response("ok")

    agency = _Agency()

    def _agency_factory(**_kwargs):
        return agency

    async def _attach_noop(_agency):
        return None

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)
    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)

    await handler(
        BaseRequest(
            message="first",
            client_config=ClientConfig(api_key="sk-request-key", base_url="https://api.openai.com/v1"),
        ),
        token=None,
    )
    await handler(BaseRequest(message="second"), token=None)

    assert seen_api_keys == ["sk-request-key", "sk-env-default"]


@pytest.mark.asyncio
async def test_make_response_endpoint_passes_request_client_to_chat_name_generator(monkeypatch) -> None:
    """generate_chat_name should use request-scoped client overrides when enabled."""
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    captured: dict[str, str | None] = {"api_key": None}

    class _ThreadManager:
        def get_all_messages(self):
            return []

    class _Response:
        def __init__(self, final_output):
            self.final_output = final_output

    class _Agency:
        def __init__(self):
            self.agents = {}
            self.thread_manager = _ThreadManager()

        async def get_response(self, **_kwargs):
            return _Response("ok")

    agency = _Agency()

    def _agency_factory(**_kwargs):
        return agency

    async def _attach_noop(_agency):
        return None

    async def _fake_generate_chat_name(_messages, openai_client=None):
        captured["api_key"] = None if openai_client is None else openai_client.api_key
        return "Sample Chat Name"

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)
    monkeypatch.setattr(endpoint_handlers, "generate_chat_name", _fake_generate_chat_name)

    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)
    response = await handler(
        BaseRequest(
            message="hello",
            generate_chat_name=True,
            client_config=ClientConfig(api_key="sk-request-key", base_url="https://api.openai.com/v1"),
        ),
        token=None,
    )

    assert response["chat_name"] == "Sample Chat Name"
    assert captured["api_key"] == "sk-request-key"


@pytest.mark.asyncio
async def test_make_response_endpoint_uses_existing_client_for_chat_name_headers_only(monkeypatch) -> None:
    """default_headers-only requests should keep agent OpenAI auth for chat-name generation."""
    pytest.importorskip("agents")

    from openai import AsyncOpenAI

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    captured = {
        "api_key": None,
        "default_headers": None,
    }

    class _ThreadManager:
        def get_all_messages(self):
            return []

    class _Response:
        def __init__(self, final_output):
            self.final_output = final_output

    class _Model:
        def __init__(self):
            self.openai_client = AsyncOpenAI(api_key="sk-agent", base_url="https://api.agent.test/v1")

    class _AgentState:
        def __init__(self):
            self.model = _Model()
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

    async def _fake_generate_chat_name(_messages, openai_client=None):
        assert openai_client is not None
        captured["api_key"] = openai_client.api_key
        captured["default_headers"] = dict(openai_client.default_headers or {})
        return "Sample Chat Name"

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)
    monkeypatch.setattr(endpoint_handlers, "apply_openai_client_config", lambda _agency, _config: None)
    monkeypatch.setattr(endpoint_handlers, "generate_chat_name", _fake_generate_chat_name)

    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)
    response = await handler(
        BaseRequest(
            message="hello",
            generate_chat_name=True,
            client_config=ClientConfig(default_headers={"x-request-id": "req-1"}),
        ),
        token=None,
    )

    assert response["chat_name"] == "Sample Chat Name"
    assert captured["api_key"] == "sk-agent"
    assert captured["default_headers"]["x-request-id"] == "req-1"

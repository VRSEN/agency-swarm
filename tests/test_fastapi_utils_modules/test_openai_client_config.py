"""Minimal tests for FastAPI request models that include `client_config`.

The end-to-end behavior is covered in integration tests under `tests/integration/fastapi/`.
"""

import asyncio
import gc
from weakref import WeakKeyDictionary

import pytest
from pydantic import ValidationError

from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig


class TestClientConfig:
    """Tests for ClientConfig model."""

    def test_config_with_all_fields(self) -> None:
        """Config accepts both base_url and api_key."""
        config = ClientConfig(
            base_url="https://custom.api.com",
            api_key="sk-custom-key",
        )
        assert config.base_url == "https://custom.api.com"
        assert config.api_key == "sk-custom-key"

    def test_config_with_only_base_url(self) -> None:
        """Config can specify only base_url."""
        config = ClientConfig(base_url="https://custom.api.com")
        assert config.base_url == "https://custom.api.com"
        assert config.api_key is None

    def test_config_with_only_api_key(self) -> None:
        """Config can specify only api_key."""
        config = ClientConfig(api_key="sk-custom-key")
        assert config.base_url is None
        assert config.api_key == "sk-custom-key"

    def test_config_empty(self) -> None:
        """Config can be created with no overrides."""
        config = ClientConfig()
        assert config.base_url is None
        assert config.api_key is None
        assert config.default_headers is None
        assert config.litellm_keys is None

    def test_config_with_litellm_keys(self) -> None:
        """Config accepts litellm_keys when LiteLLM is available."""
        try:
            config = ClientConfig(
                litellm_keys={
                    "anthropic": "sk-ant-xxx",
                    "gemini": "AIza...",
                }
            )
        except ValidationError as exc:
            assert "litellm_keys requires litellm to be installed" in str(exc)
            return
        assert config.litellm_keys is not None
        assert config.litellm_keys["anthropic"] == "sk-ant-xxx"
        assert config.litellm_keys["gemini"] == "AIza..."


class TestBaseRequestWithClientConfig:
    """Tests for BaseRequest including client_config."""

    def test_request_without_client_config(self) -> None:
        """Request works without client config."""
        request = BaseRequest(message="Hello")
        assert request.client_config is None

    def test_request_with_client_config(self) -> None:
        """Request accepts client config."""
        request = BaseRequest(
            message="Hello",
            client_config=ClientConfig(
                base_url="https://custom.api.com",
                api_key="sk-custom-key",
                default_headers={"x-test": "1"},
            ),
        )
        assert request.client_config is not None
        assert request.client_config.base_url == "https://custom.api.com"
        assert request.client_config.api_key == "sk-custom-key"
        assert request.client_config.default_headers == {"x-test": "1"}


def test_request_api_key_allows_client_build_without_env(monkeypatch) -> None:
    """Request api_key should work even if server has no OPENAI_API_KEY."""
    pytest.importorskip("agents")

    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Common setup: model is a plain string, so there is no embedded OpenAI client.
    agent = Agent(name="TestAgent", instructions="x", model="gpt-4o-mini")
    cfg = ClientConfig(api_key="sk-test", base_url="http://example.invalid", default_headers={"x-test": "1"})

    client = endpoint_handlers._build_openai_client_for_agent(agent, cfg)
    assert isinstance(client, AsyncOpenAI)
    assert client.api_key == "sk-test"
    assert str(client.base_url).startswith("http://example.invalid")


def test_default_headers_only_without_baseline_client_does_not_raise(monkeypatch) -> None:
    """Headers-only config should not fail when there is no existing OpenAI client to copy."""
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    class _AgentState:
        def __init__(self) -> None:
            self.name = "A"
            self.model = "gpt-4o-mini"
            self.model_settings = None

    class _Agency:
        def __init__(self) -> None:
            self.agents = {"A": _AgentState()}

    agency = _Agency()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(endpoint_handlers, "get_default_openai_client", lambda: None)

    apply_openai_client_config(agency, ClientConfig(default_headers={"x-request-id": "req-1"}))

    assert agency.agents["A"].model == "gpt-4o-mini"


def test_default_headers_only_does_not_override_litellm_model_settings() -> None:
    """default_headers-only should not rebuild LitellmModel, and should add headers to model_settings."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    class _Agency:
        def __init__(self, agent: Agent):
            self.agents = {"A": agent}

    original_model = LitellmModel(model="anthropic/claude-sonnet-4", base_url="http://litellm.local", api_key="k1")
    agent = Agent(name="A", instructions="x", model=original_model)
    agency = _Agency(agent)

    apply_openai_client_config(agency, ClientConfig(default_headers={"x-test": "1"}))

    # Must remain intact
    assert isinstance(agent.model, LitellmModel)
    assert agent.model.base_url == "http://litellm.local"
    assert agent.model.api_key == "k1"
    assert agent.model_settings is not None
    assert agent.model_settings.extra_headers is not None
    assert agent.model_settings.extra_headers["x-test"] == "1"


def test_litellm_anthropic_does_not_use_generic_api_key_fallback() -> None:
    """config.api_key should not override Anthropic auth unless litellm_keys is provided."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    class _Agency:
        def __init__(self, agent: Agent):
            self.agents = {"A": agent}

    # Existing LitellmModel has no api_key -> should rely on provider env.
    original_model = LitellmModel(model="anthropic/claude-sonnet-4", base_url="http://litellm.local", api_key=None)
    agent = Agent(name="A", instructions="x", model=original_model)
    agency = _Agency(agent)

    apply_openai_client_config(agency, ClientConfig(api_key="sk-openai-gateway", base_url="http://gw"))

    assert isinstance(agent.model, LitellmModel)
    assert agent.model.model == "anthropic/claude-sonnet-4"
    # Must not be overridden with the OpenAI gateway key.
    assert agent.model.api_key is None


def test_litellm_openai_provider_can_use_generic_api_key_fallback() -> None:
    """For openai-ish LiteLLM providers, config.api_key remains a valid fallback."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    class _Agency:
        def __init__(self, agent: Agent):
            self.agents = {"A": agent}

    original_model = LitellmModel(model="openai/gpt-4o-mini", base_url=None, api_key=None)
    agent = Agent(name="A", instructions="x", model=original_model)
    agency = _Agency(agent)

    apply_openai_client_config(agency, ClientConfig(api_key="sk-openai", base_url="http://gw"))

    assert isinstance(agent.model, LitellmModel)
    assert agent.model.api_key == "sk-openai"


def test_snapshot_restore_preserves_model_settings_headers() -> None:
    """Snapshot/restore should not leak mutated model_settings."""
    pytest.importorskip("agents")

    from agents import ModelSettings

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import (
        _apply_default_headers_to_agent_model_settings,
        _restore_agency_state,
        _snapshot_agency_state,
    )

    class _Agency:
        def __init__(self, agent: Agent):
            self.agents = {"A": agent}

    agent = Agent(name="A", instructions="x", model="gpt-4o-mini")
    agent.model_settings = ModelSettings(extra_headers={"x-orig": "1"})
    agency = _Agency(agent)

    snapshot = _snapshot_agency_state(agency)
    _apply_default_headers_to_agent_model_settings(agent, {"x-orig": "2", "x-new": "3"})

    _restore_agency_state(agency, snapshot)

    assert agent.model_settings.extra_headers == {"x-orig": "1"}


def test_non_openai_custom_model_skips_openai_client_build(monkeypatch) -> None:
    """Custom non-OpenAI model names should skip OpenAI client construction entirely."""
    pytest.importorskip("agents")

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    class _Agency:
        def __init__(self, agent: Agent):
            self.agents = {"A": agent}

    agent = Agent(name="A", instructions="x", model="anthropic/claude-3-5-sonnet")
    agency = _Agency(agent)

    def _boom(*_args, **_kwargs):
        raise AssertionError("_build_openai_client_for_agent should not be called for unsupported models")

    monkeypatch.setattr(endpoint_handlers, "_build_openai_client_for_agent", _boom)

    # Should not raise; unsupported custom models are skipped.
    endpoint_handlers.apply_openai_client_config(agency, ClientConfig(default_headers={"x-test": "1"}))


@pytest.mark.asyncio
async def test_make_response_endpoint_passes_request_client_to_file_upload(monkeypatch) -> None:
    """file_urls upload should use request-level OpenAI client overrides."""
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    captured = {
        "api_key": None,
        "base_url": None,
        "default_headers": None,
    }

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

    async def _fake_upload_from_urls(_file_urls, allowed_local_dirs=None, openai_client=None):
        del allowed_local_dirs  # not relevant for this test
        assert openai_client is not None
        captured["api_key"] = openai_client.api_key
        captured["base_url"] = str(openai_client.base_url)
        captured["default_headers"] = dict(openai_client.default_headers or {})
        return {"doc.txt": "file-123"}

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)
    monkeypatch.setattr(endpoint_handlers, "apply_openai_client_config", lambda _agency, _config: None)
    monkeypatch.setattr(endpoint_handlers, "upload_from_urls", _fake_upload_from_urls)

    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)
    request = BaseRequest(
        message="hello",
        file_urls={"doc.txt": "https://example.com/doc.txt"},
        client_config=ClientConfig(
            api_key="sk-request-key",
            base_url="https://api.example.test/v1",
            default_headers={"x-request-id": "req-1"},
        ),
    )

    response = await handler(request, token=None)
    assert response["file_ids_map"] == {"doc.txt": "file-123"}
    assert captured["api_key"] == "sk-request-key"
    assert captured["base_url"].startswith("https://api.example.test/v1")
    assert captured["default_headers"]["x-request-id"] == "req-1"


@pytest.mark.asyncio
async def test_make_response_endpoint_uses_existing_client_for_file_upload_headers_only(monkeypatch) -> None:
    """default_headers-only requests should keep the agent's existing OpenAI auth for uploads."""
    pytest.importorskip("agents")

    from openai import AsyncOpenAI

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    captured = {
        "api_key": None,
        "base_url": None,
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

    async def _fake_upload_from_urls(_file_urls, allowed_local_dirs=None, openai_client=None):
        del allowed_local_dirs
        assert openai_client is not None
        captured["api_key"] = openai_client.api_key
        captured["base_url"] = str(openai_client.base_url)
        captured["default_headers"] = dict(openai_client.default_headers or {})
        return {"doc.txt": "file-123"}

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)
    monkeypatch.setattr(endpoint_handlers, "apply_openai_client_config", lambda _agency, _config: None)
    monkeypatch.setattr(endpoint_handlers, "upload_from_urls", _fake_upload_from_urls)

    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)
    request = BaseRequest(
        message="hello",
        file_urls={"doc.txt": "https://example.com/doc.txt"},
        client_config=ClientConfig(default_headers={"x-request-id": "req-1"}),
    )

    response = await handler(request, token=None)
    assert response["file_ids_map"] == {"doc.txt": "file-123"}
    assert captured["api_key"] == "sk-agent"
    assert captured["base_url"].startswith("https://api.agent.test/v1")
    assert captured["default_headers"]["x-request-id"] == "req-1"


@pytest.mark.asyncio
async def test_make_response_endpoint_uses_recipient_agent_client_for_uploads(monkeypatch) -> None:
    """Upload client should be derived from the selected recipient agent context."""
    pytest.importorskip("agents")

    from openai import AsyncOpenAI

    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    captured: dict[str, str | None] = {"api_key": None}

    class _ThreadManager:
        def get_all_messages(self):
            return []

    class _Response:
        def __init__(self, final_output):
            self.final_output = final_output

    class _Model:
        def __init__(self, api_key: str):
            self.openai_client = AsyncOpenAI(api_key=api_key, base_url="https://api.agent.test/v1")

    class _AgentState:
        def __init__(self, api_key: str):
            self.model = _Model(api_key=api_key)
            self.model_settings = None

    class _Agency:
        def __init__(self):
            self.agents = {
                "FirstAgent": _AgentState(api_key="sk-first"),
                "TargetAgent": _AgentState(api_key="sk-target"),
            }
            self.thread_manager = _ThreadManager()

        async def get_response(self, **_kwargs):
            return _Response("ok")

    agency = _Agency()

    def _agency_factory(**_kwargs):
        return agency

    async def _attach_noop(_agency):
        return None

    async def _fake_upload_from_urls(_file_urls, allowed_local_dirs=None, openai_client=None):
        del allowed_local_dirs
        assert openai_client is not None
        captured["api_key"] = openai_client.api_key
        return {"doc.txt": "file-123"}

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)
    monkeypatch.setattr(endpoint_handlers, "apply_openai_client_config", lambda _agency, _config: None)
    monkeypatch.setattr(endpoint_handlers, "upload_from_urls", _fake_upload_from_urls)

    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)
    response = await handler(
        BaseRequest(
            message="hello",
            recipient_agent="TargetAgent",
            file_urls={"doc.txt": "https://example.com/doc.txt"},
            client_config=ClientConfig(default_headers={"x-request-id": "req-1"}),
        ),
        token=None,
    )

    assert response["file_ids_map"] == {"doc.txt": "file-123"}
    assert captured["api_key"] == "sk-target"


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
async def test_make_stream_endpoint_serializes_singleton_agency_requests(monkeypatch) -> None:
    """Concurrent stream requests against a cached agency should be serialized by the handler."""
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
            self._in_flight = 0
            self.max_in_flight = 0

        def get_response_stream(self, **_kwargs):
            async def _stream():
                self._in_flight += 1
                self.max_in_flight = max(self.max_in_flight, self._in_flight)
                await asyncio.sleep(0.05)
                self._in_flight -= 1
                if False:
                    yield {}

            return StreamingRunResponse(_stream())

    agency = _Agency()

    def _agency_factory(**_kwargs):
        return agency

    async def _attach_noop(_agency):
        return None

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)
    monkeypatch.setattr(endpoint_handlers, "apply_openai_client_config", lambda _agency, _config: None)

    handler = make_stream_endpoint(
        BaseRequest,
        _agency_factory,
        verify_token=lambda: None,
        run_registry=ActiveRunRegistry(),
    )

    request_a = BaseRequest(message="a", client_config=ClientConfig(default_headers={"x-request": "a"}))
    # No client_config on the second request to verify mixed traffic is still serialized.
    request_b = BaseRequest(message="b")

    async def _run_request(request: BaseRequest) -> None:
        response = await handler(http_request=_HttpRequest(), request=request, token=None)
        _chunks = [chunk async for chunk in response.body_iterator]

    await asyncio.gather(_run_request(request_a), _run_request(request_b))

    assert agency.max_in_flight == 1


@pytest.mark.asyncio
async def test_make_stream_endpoint_builds_upload_client_after_lease(monkeypatch) -> None:
    """Streaming upload client derivation must happen only after lease acquisition."""
    pytest.importorskip("agents")

    from agency_swarm.agent.execution_stream_response import StreamingRunResponse
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import ActiveRunRegistry, make_stream_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    lease_acquired = False
    upload_client = object()

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

    handler = make_stream_endpoint(
        BaseRequest,
        _agency_factory,
        verify_token=lambda: None,
        run_registry=ActiveRunRegistry(),
    )
    response = await handler(
        http_request=_HttpRequest(),
        request=BaseRequest(
            message="hello",
            file_urls={"doc.txt": "https://example.com/doc.txt"},
            client_config=ClientConfig(default_headers={"x-request-id": "req-1"}),
        ),
        token=None,
    )
    _chunks = [chunk async for chunk in response.body_iterator]


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


@pytest.mark.asyncio
async def test_make_agui_endpoint_serializes_singleton_agency_requests(monkeypatch) -> None:
    """Concurrent AG-UI requests against a cached agency should be serialized by the handler."""
    pytest.importorskip("agents")

    from types import SimpleNamespace

    from agency_swarm.agent.execution_stream_response import StreamingRunResponse
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_agui_chat_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    class _ThreadManager:
        def get_all_messages(self):
            return []

    class _AgentState:
        def __init__(self):
            self.model = "gpt-4o-mini"
            self.model_settings = None
            self.name = "A"

    class _Message:
        def __init__(self, content: str):
            self.content = content

        def model_dump(self):
            return {"role": "user", "content": self.content}

    class _Request:
        def __init__(self, content: str):
            self.thread_id = "thread-1"
            self.run_id = f"run-{content}"
            self.state = None
            self.messages = [_Message(content)]
            self.tools = []
            self.context = []
            self.forwarded_props = None
            self.chat_history = None
            self.additional_instructions = None
            self.user_context = None
            self.file_ids = None
            self.file_urls = None
            self.client_config = ClientConfig(default_headers={"x-request": content}) if content == "a" else None

    class _Agency:
        def __init__(self):
            self.agents = {"A": _AgentState()}
            self.thread_manager = _ThreadManager()
            self.entry_points = [SimpleNamespace(name="A")]
            self._in_flight = 0
            self.max_in_flight = 0

        def get_response_stream(self, **_kwargs):
            async def _stream():
                self._in_flight += 1
                self.max_in_flight = max(self.max_in_flight, self._in_flight)
                await asyncio.sleep(0.05)
                self._in_flight -= 1
                if False:
                    yield {}

            return StreamingRunResponse(_stream())

    agency = _Agency()

    def _agency_factory(**_kwargs):
        return agency

    async def _attach_noop(_agency):
        return None

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)
    monkeypatch.setattr(endpoint_handlers, "apply_openai_client_config", lambda _agency, _config: None)

    handler = make_agui_chat_endpoint(_Request, _agency_factory, verify_token=lambda: None)

    async def _run_request(content: str) -> None:
        response = await handler(_Request(content), token=None)
        _chunks = [chunk async for chunk in response.body_iterator]

    await asyncio.gather(_run_request("a"), _run_request("b"))

    assert agency.max_in_flight == 1


@pytest.mark.asyncio
async def test_make_agui_endpoint_builds_upload_client_after_lease(monkeypatch) -> None:
    """AG-UI upload client derivation must happen only after lease acquisition."""
    pytest.importorskip("agents")

    from types import SimpleNamespace

    from agency_swarm.agent.execution_stream_response import StreamingRunResponse
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_agui_chat_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    lease_acquired = False
    upload_client = object()

    class _ThreadManager:
        def get_all_messages(self):
            return []

    class _AgentState:
        def __init__(self):
            self.model = "gpt-4o-mini"
            self.model_settings = None
            self.name = "A"

    class _Message:
        def __init__(self, content: str):
            self.content = content

        def model_dump(self):
            return {"role": "user", "content": self.content}

    class _Request:
        def __init__(self):
            self.thread_id = "thread-1"
            self.run_id = "run-1"
            self.state = None
            self.messages = [_Message("hello")]
            self.tools = []
            self.context = []
            self.forwarded_props = None
            self.chat_history = None
            self.additional_instructions = None
            self.user_context = None
            self.file_ids = None
            self.file_urls = {"doc.txt": "https://example.com/doc.txt"}
            self.client_config = ClientConfig(default_headers={"x-request-id": "req-1"})

    class _Agency:
        def __init__(self):
            self.agents = {"A": _AgentState()}
            self.thread_manager = _ThreadManager()
            self.entry_points = [SimpleNamespace(name="A")]

        def get_response_stream(self, **_kwargs):
            async def _stream():
                if False:
                    yield {}

            return StreamingRunResponse(_stream())

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

    handler = make_agui_chat_endpoint(_Request, _agency_factory, verify_token=lambda: None)
    response = await handler(_Request(), token=None)
    _chunks = [chunk async for chunk in response.body_iterator]

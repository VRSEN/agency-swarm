"""Minimal tests for FastAPI request models that include `client_config`.

The end-to-end behavior is covered in integration tests under `tests/integration/fastapi/`.
"""

import logging
from types import SimpleNamespace

import pytest

from agency_swarm.integrations.fastapi_utils import endpoint_handlers, request_models
from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"base_url": "https://custom.api.com", "api_key": "sk-custom-key"},
            {"base_url": "https://custom.api.com", "api_key": "sk-custom-key"},
        ),
        (
            {"base_url": "https://custom.api.com"},
            {"base_url": "https://custom.api.com", "api_key": None},
        ),
        (
            {"api_key": "sk-custom-key"},
            {"base_url": None, "api_key": "sk-custom-key"},
        ),
        (
            {},
            {
                "base_url": None,
                "api_key": None,
                "default_headers": None,
                "litellm_keys": None,
                "model": None,
            },
        ),
    ],
)
def test_client_config_accepts_optional_overrides(payload: dict, expected: dict) -> None:
    """Client config should accept partial override payloads without extra scaffolding."""
    config = ClientConfig(**payload)
    for key, value in expected.items():
        assert getattr(config, key) == value


def test_client_config_accepts_litellm_keys_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """litellm_keys should round-trip when litellm is available."""
    monkeypatch.setattr(request_models, "_LITELLM_INSTALLED", True)
    config = ClientConfig(
        litellm_keys={
            "anthropic": "sk-ant-xxx",
            "gemini": "AIza...",
        }
    )
    assert config.litellm_keys is not None
    assert config.litellm_keys["anthropic"] == "sk-ant-xxx"
    assert config.litellm_keys["gemini"] == "AIza..."


def test_client_config_drops_litellm_keys_when_litellm_missing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Without litellm, litellm_keys should be dropped (not 422'd) and a warning logged."""
    monkeypatch.setattr(request_models, "_LITELLM_INSTALLED", False)
    with caplog.at_level(logging.WARNING, logger=request_models.__name__):
        config = ClientConfig(litellm_keys={"anthropic": "sk-ant-xxx"})
    assert config.litellm_keys is None
    assert any("litellm is not installed" in record.message for record in caplog.records)


def test_base_request_client_config_roundtrip() -> None:
    """Base request should preserve parsed client_config values."""
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


def test_tui_bridge_stream_config_ignores_default_model_sentinel() -> None:
    """The TUI bridge sentinel must not replace the agency's configured model."""
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(agency_swarm_tui_bridge=True)))
    config = ClientConfig(model="agency-swarm/default", api_key="sk-test", default_headers={"x-test": "1"})

    resolved = endpoint_handlers._resolve_stream_client_config(request, config)

    assert resolved is not None
    assert resolved.model is None
    assert resolved.api_key == "sk-test"
    assert resolved.default_headers == {"x-test": "1"}


def test_tui_bridge_stream_config_strips_default_model_bridge_base_url() -> None:
    """The default sentinel should not point local LiteLLM agency models back at the bridge."""
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(agency_swarm_tui_bridge=True)),
        base_url="http://127.0.0.1:54321/",
    )
    config = ClientConfig(
        model="agency-swarm/default",
        api_key="sk-test",
        base_url="http://127.0.0.1:54321",
    )

    resolved = endpoint_handlers._resolve_stream_client_config(request, config)

    assert resolved is not None
    assert resolved.model is None
    assert resolved.base_url is None
    assert resolved.api_key == "sk-test"
    assert config.base_url == "http://127.0.0.1:54321"


def test_tui_bridge_stream_config_keeps_explicit_openai_model() -> None:
    """TUI-selected OpenAI models should replace the agency's configured model."""
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(agency_swarm_tui_bridge=True)))
    config = ClientConfig(model="gpt-5.4", api_key="sk-test")

    resolved = endpoint_handlers._resolve_stream_client_config(request, config)

    assert resolved is config
    assert resolved.model == "gpt-5.4"


def test_regular_stream_config_keeps_request_model() -> None:
    """Non-TUI FastAPI callers must retain explicit request model overrides."""
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    config = ClientConfig(model="gpt-5.4", api_key="sk-test")

    resolved = endpoint_handlers._resolve_stream_client_config(request, config)

    assert resolved is config
    assert resolved.model == "gpt-5.4"


def test_regular_stream_config_keeps_default_model_sentinel_without_app() -> None:
    """Non-TUI stream request doubles without ``.app`` should keep the sentinel."""
    request = SimpleNamespace()
    config = ClientConfig(model="agency-swarm/default", api_key="sk-test")

    resolved = endpoint_handlers._resolve_stream_client_config(request, config)

    assert resolved is config
    assert resolved.model == "agency-swarm/default"


def test_regular_stream_config_keeps_default_model_sentinel_without_tui_bridge() -> None:
    """Only the TUI bridge should strip the default-model sentinel."""
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    config = ClientConfig(model="agency-swarm/default", api_key="sk-test")

    resolved = endpoint_handlers._resolve_stream_client_config(request, config)

    assert resolved is config
    assert resolved.model == "agency-swarm/default"


def test_tui_bridge_stream_config_keeps_explicit_litellm_model() -> None:
    """TUI-selected LiteLLM models should replace the agency's configured model."""
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(agency_swarm_tui_bridge=True)))
    config = ClientConfig(model="litellm/ollama_chat/gemma4:e4b")

    resolved = endpoint_handlers._resolve_stream_client_config(request, config)

    assert resolved is config
    assert resolved.model == "litellm/ollama_chat/gemma4:e4b"


def test_tui_bridge_stream_config_strips_local_litellm_gateway_base_url() -> None:
    """TUI-selected local LiteLLM models should not inherit the bridge server URL."""
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(agency_swarm_tui_bridge=True)),
        base_url="http://127.0.0.1:54321/",
    )
    config = ClientConfig(
        model="litellm/ollama_chat/gemma4:e4b",
        api_key="sk-openai-gateway",
        base_url="http://127.0.0.1:54321",
    )

    resolved = endpoint_handlers._resolve_stream_client_config(request, config)

    assert resolved is not None
    assert resolved is not config
    assert resolved.model == "litellm/ollama_chat/gemma4:e4b"
    assert resolved.base_url is None
    assert resolved.api_key == "sk-openai-gateway"
    assert config.base_url == "http://127.0.0.1:54321"


def test_tui_bridge_stream_config_preserves_explicit_local_litellm_base_url() -> None:
    """Remote Ollama/LM Studio base URLs must survive the TUI bridge rewrite."""
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(agency_swarm_tui_bridge=True)),
        base_url="http://127.0.0.1:54321/",
    )
    config = ClientConfig(
        model="litellm/ollama_chat/gemma4:e4b",
        api_key="sk-openai-gateway",
        base_url="http://remote-ollama.test",
    )

    resolved = endpoint_handlers._resolve_stream_client_config(request, config)

    assert resolved is config
    assert resolved.base_url == "http://remote-ollama.test"


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


def test_default_headers_only_without_baseline_client_falls_back_to_model_settings(monkeypatch) -> None:
    """When there is no baseline client, default_headers must still reach model_settings.extra_headers."""
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

    # Model stays a string — no client was built — but headers must reach model_settings.
    assert agency.agents["A"].model == "gpt-4o-mini"
    assert agency.agents["A"].model_settings is not None
    assert agency.agents["A"].model_settings.extra_headers == {"x-request-id": "req-1"}


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
    assert agent.model.base_url == "http://gw"


def test_litellm_anthropic_does_not_use_codex_base_url_fallback() -> None:
    """Codex browser-auth base_url must not override non-OpenAI LiteLLM providers."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    class _Agency:
        def __init__(self, agent: Agent):
            self.agents = {"A": agent}

    original_model = LitellmModel(model="anthropic/claude-sonnet-4", base_url=None, api_key=None)
    agent = Agent(name="A", instructions="x", model=original_model)
    agency = _Agency(agent)

    apply_openai_client_config(
        agency,
        ClientConfig(
            api_key="sk-openai-gateway",
            base_url="https://chatgpt.com/backend-api/codex",
            litellm_keys={"anthropic": "sk-ant"},
        ),
    )

    assert isinstance(agent.model, LitellmModel)
    assert agent.model.model == "anthropic/claude-sonnet-4"
    assert agent.model.base_url is None
    assert agent.model.api_key == "sk-ant"


def test_litellm_google_wrapper_uses_gemini_request_key() -> None:
    """Existing Google Gemini LiteLLM wrappers should resolve keys against Gemini."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    class _Agency:
        def __init__(self, agent: Agent):
            self.agents = {"A": agent}

    original_model = LitellmModel(model="google/gemini-2.5-pro", base_url=None, api_key=None)
    agent = Agent(name="A", instructions="x", model=original_model)
    agency = _Agency(agent)

    apply_openai_client_config(agency, ClientConfig(litellm_keys={"gemini": "AIza-request"}))

    assert isinstance(agent.model, LitellmModel)
    assert agent.model.model == "google/gemini-2.5-pro"
    assert agent.model.api_key == "AIza-request"


def test_litellm_google_wrapper_uses_gemini_request_proxy_base_url() -> None:
    """Explicit LiteLLM proxy base_url should still reach Gemini wrappers."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    class _Agency:
        def __init__(self, agent: Agent):
            self.agents = {"A": agent}

    original_model = LitellmModel(model="google/gemini-2.5-pro", base_url=None, api_key=None)
    agent = Agent(name="A", instructions="x", model=original_model)
    agency = _Agency(agent)

    apply_openai_client_config(
        agency,
        ClientConfig(base_url="http://litellm-proxy.local", litellm_keys={"gemini": "AIza-request"}),
    )

    assert isinstance(agent.model, LitellmModel)
    assert agent.model.model == "google/gemini-2.5-pro"
    assert agent.model.api_key == "AIza-request"
    assert agent.model.base_url == "http://litellm-proxy.local"


def test_litellm_ollama_uses_explicit_request_base_url() -> None:
    """Non-TUI callers may route local LiteLLM providers to a remote Ollama endpoint."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    class _Agency:
        def __init__(self, agent: Agent):
            self.agents = {"A": agent}

    original_model = LitellmModel(model="ollama_chat/gemma4:e4b", base_url=None, api_key=None)
    agent = Agent(name="A", instructions="x", model=original_model)
    agency = _Agency(agent)

    apply_openai_client_config(agency, ClientConfig(api_key="sk-openai-gateway", base_url="http://remote-ollama.test"))

    assert isinstance(agent.model, LitellmModel)
    assert agent.model.model == "ollama_chat/gemma4:e4b"
    assert agent.model.base_url == "http://remote-ollama.test"
    assert agent.model.api_key is None


def test_agency_swarm_default_model_override_reaches_litellm_agent_model() -> None:
    """Outside the TUI stream bridge, the sentinel remains a normal model override."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    class _Agency:
        def __init__(self, agent: Agent):
            self.agents = {"A": agent}

    original_model = LitellmModel(model="ollama_chat/gemma4:e4b", base_url="http://localhost:11434/", api_key=None)
    agent = Agent(name="A", instructions="x", model=original_model)
    agency = _Agency(agent)

    apply_openai_client_config(agency, ClientConfig(model="agency-swarm/default"))

    assert isinstance(agent.model, LitellmModel)
    assert agent.model is not original_model
    assert agent.model.model == "agency-swarm/default"
    assert agent.model.base_url == "http://localhost:11434/"


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


def test_openai_client_override_applies_codex_compatibility_model_settings() -> None:
    """Codex overrides should use the Responses settings the browser-auth backend accepts."""
    pytest.importorskip("agents")

    from agents import OpenAIResponsesModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    class _Agency:
        def __init__(self, agent: Agent):
            self.agents = {"A": agent}

    agent = Agent(name="A", instructions="x", model="gpt-4o-mini")
    agency = _Agency(agent)

    apply_openai_client_config(
        agency,
        ClientConfig(api_key="sk-openai", base_url="https://chatgpt.com/backend-api/codex"),
    )

    assert isinstance(agent.model, OpenAIResponsesModel)
    assert agent.model_settings is not None
    assert agent.model_settings.store is False
    assert agent.model_settings.truncation is None
    assert "reasoning.encrypted_content" in (agent.model_settings.response_include or [])


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


def test_model_override_applies_to_all_agents() -> None:
    """client_config.model should replace every agent's model for the request."""
    pytest.importorskip("agents")

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    a1 = Agent(name="A1", instructions="x", model="gpt-4o-mini")
    a2 = Agent(name="A2", instructions="y", model="gpt-4o")
    agency = type("Agency", (), {"agents": {"A1": a1, "A2": a2}})()

    apply_openai_client_config(agency, ClientConfig(model="gpt-4.1"))

    assert a1.model == "gpt-4.1"
    assert a2.model == "gpt-4.1"


@pytest.mark.parametrize(
    "model",
    [
        "litellm/ollama_chat/gemma4:e4b",
        "anthropic/claude-sonnet-4-6",
        "openrouter/anthropic/claude-sonnet-4.5",
        "openrouter/openai/gpt-5",
    ],
)
def test_non_openai_model_override_strips_openai_hosted_tools(model: str) -> None:
    """Non-OpenAI request model overrides must not send OpenAI hosted tools."""
    pytest.importorskip("agents")

    from agents import ToolSearchTool, WebSearchTool, function_tool

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    @function_tool
    def local_lookup() -> str:
        return "ok"

    hosted = WebSearchTool()
    tool_search = ToolSearchTool()
    agent = Agent(name="A", instructions="x", model="gpt-4o-mini", tools=[hosted, tool_search, local_lookup])
    agency = type("Agency", (), {"agents": {"A": agent}})()

    config = (
        ClientConfig(model=model, api_key="sk-openrouter")
        if model.startswith("openrouter/")
        else ClientConfig(model=model)
    )
    apply_openai_client_config(agency, config)

    assert hosted not in agent.tools
    assert tool_search not in agent.tools
    assert any(getattr(tool, "name", "") == "local_lookup" for tool in agent.tools)
    assert "web_search_call.action.sources" not in (agent.model_settings.response_include or [])


def test_configured_openrouter_request_without_model_override_strips_openai_hosted_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured OpenRouter agents should strip hosted tools for request-scoped gateway routes."""
    pytest.importorskip("agents")

    from agents import ToolSearchTool, WebSearchTool, function_tool

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    @function_tool
    def local_lookup() -> str:
        return "ok"

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-original")

    hosted = WebSearchTool()
    tool_search = ToolSearchTool()
    agent = Agent(
        name="A",
        instructions="x",
        model="openrouter/anthropic/claude-sonnet-4.5",
        tools=[hosted, tool_search, local_lookup],
    )
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(api_key="sk-openrouter", base_url="https://openrouter-proxy.test/v1"),
    )

    assert hosted not in agent.tools
    assert tool_search not in agent.tools
    assert any(getattr(tool, "name", "") == "local_lookup" for tool in agent.tools)
    assert "web_search_call.action.sources" not in (agent.model_settings.response_include or [])


@pytest.mark.parametrize("model", ["gpt-5", "openai/gpt-4o-mini"])
def test_openai_model_override_keeps_openai_hosted_tools(model: str) -> None:
    """OpenAI request model overrides should keep OpenAI hosted tools available."""
    pytest.importorskip("agents")

    from agents import ToolSearchTool, WebSearchTool

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    hosted = WebSearchTool()
    tool_search = ToolSearchTool()
    agent = Agent(name="A", instructions="x", model="gpt-4o-mini", tools=[hosted, tool_search])
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model=model))

    assert hosted in agent.tools
    assert tool_search in agent.tools
    assert "web_search_call.action.sources" in (agent.model_settings.response_include or [])


def test_snapshot_restore_preserves_tools_after_non_openai_model_override() -> None:
    """Request cleanup should restore hosted tools stripped from non-OpenAI runs."""
    pytest.importorskip("agents")

    from agents import ToolSearchTool, WebSearchTool, function_tool

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import (
        _restore_agency_state,
        _snapshot_agency_state,
        apply_openai_client_config,
    )
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    @function_tool
    def local_lookup() -> str:
        return "ok"

    hosted = WebSearchTool()
    tool_search = ToolSearchTool()
    agent = Agent(name="A", instructions="x", model="gpt-4o-mini", tools=[hosted, tool_search, local_lookup])
    agency = type("Agency", (), {"agents": {"A": agent}})()
    original_tools = list(agent.tools)

    snapshot = _snapshot_agency_state(agency)
    apply_openai_client_config(agency, ClientConfig(model="litellm/ollama_chat/gemma4:e4b"))
    assert hosted not in agent.tools
    assert tool_search not in agent.tools
    assert agent.model_settings.response_include is None

    _restore_agency_state(agency, snapshot)

    assert agent.tools == original_tools
    assert agent.model_settings.response_include == ["web_search_call.action.sources"]


def test_model_override_preserves_openai_responses_client() -> None:
    """config.model on an OpenAIResponsesModel agent keeps the embedded client + transport."""
    pytest.importorskip("agents")

    from agents import OpenAIResponsesModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    embedded = AsyncOpenAI(api_key="sk-agent", base_url="https://api.agent.test/v1")
    original = OpenAIResponsesModel(model="gpt-4o", openai_client=embedded)
    agent = Agent(name="A", instructions="x", model=original)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="gpt-4.1"))

    assert isinstance(agent.model, OpenAIResponsesModel)
    assert agent.model.model == "gpt-4.1"
    assert agent.model._client is embedded


def test_model_override_preserves_chat_completions_transport() -> None:
    """config.model on an OpenAIChatCompletionsModel agent keeps the ChatCompletions transport + client."""
    pytest.importorskip("agents")

    from agents import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    embedded = AsyncOpenAI(api_key="sk-agent", base_url="https://chat.agent.test/v1")
    original = OpenAIChatCompletionsModel(model="gpt-4o", openai_client=embedded)
    agent = Agent(name="A", instructions="x", model=original)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="gpt-4.1"))

    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    assert agent.model.model == "gpt-4.1"
    assert agent.model._client is embedded


def test_model_override_preserves_litellm_credentials() -> None:
    """config.model on a LitellmModel agent keeps the existing base_url + api_key."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    original = LitellmModel(model="anthropic/claude-sonnet-4", base_url="http://litellm.local", api_key="sk-existing")
    agent = Agent(name="A", instructions="x", model=original)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="litellm/anthropic/claude-opus-4"))

    assert isinstance(agent.model, LitellmModel)
    assert agent.model.model == "anthropic/claude-opus-4"
    assert agent.model.base_url == "http://litellm.local"
    assert agent.model.api_key == "sk-existing"


def test_litellm_provider_model_override_does_not_add_reasoning_settings() -> None:
    """Provider model overrides must not manufacture reasoning request parameters."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents import ModelSettings
    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model=LitellmModel(model="openai/gpt-5.4"))
    agent.model_settings = ModelSettings(extra_headers={"x-request": "1"})
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="litellm/anthropic/claude-sonnet-4-20250514"))

    assert isinstance(agent.model, LitellmModel)
    assert agent.model.model == "anthropic/claude-sonnet-4-20250514"
    assert agent.model_settings.reasoning is None
    assert agent.model_settings.extra_headers == {"x-request": "1"}


def test_xai_model_override_does_not_add_reasoning_settings() -> None:
    """xAI Grok models reject LiteLLM reasoningEffort, so do not manufacture it."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model=LitellmModel(model="openai/gpt-5.4"))
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="litellm/xai/grok-4.20-0309-reasoning"))

    assert isinstance(agent.model, LitellmModel)
    assert agent.model.model == "xai/grok-4.20-0309-reasoning"
    assert agent.model_settings.reasoning is None


def test_litellm_model_override_applies_explicit_variant_extra_args() -> None:
    """User-selected model variants should pass provider settings without backend defaults."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model=LitellmModel(model="openai/gpt-5.4"))
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="litellm/anthropic/claude-sonnet-4-20250514",
            model_settings_extra_args={
                "thinking": {"type": "enabled", "budgetTokens": 16000},
                "reasoning_effort": "high",
            },
        ),
    )

    assert isinstance(agent.model, LitellmModel)
    assert agent.model.model == "anthropic/claude-sonnet-4-20250514"
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "high"
    assert agent.model_settings.extra_args == {
        "thinking": {"type": "enabled", "budget_tokens": 16000},
        "reasoning_effort": "high",
    }


def test_litellm_anthropic_variant_maps_effort_without_leaking_provider_field() -> None:
    """Anthropic UI variants use effort, but LiteLLM expects reasoning_effort."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model=LitellmModel(model="anthropic/claude-sonnet-4-6"))
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="litellm/anthropic/claude-sonnet-4-6",
            model_settings_extra_args={
                "thinking": {"type": "adaptive"},
                "effort": "high",
                "reasoning_summary": "auto",
            },
        ),
    )

    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "high"
    assert agent.model_settings.extra_args == {
        "thinking": {"type": "adaptive"},
        "reasoning_effort": "high",
    }


def test_litellm_gemini_variant_maps_thinking_config() -> None:
    """Gemini UI variants use thinkingConfig, but LiteLLM expects thinking or reasoning_effort."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model=LitellmModel(model="google/gemini-2.5-pro"))
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="litellm/google/gemini-2.5-pro",
            model_settings_extra_args={
                "thinkingConfig": {"includeThoughts": True, "thinkingBudget": 16000},
            },
        ),
    )

    assert isinstance(agent.model, LitellmModel)
    assert agent.model.model == "gemini/gemini-2.5-pro"
    assert agent.model_settings.reasoning is None
    assert agent.model_settings.extra_args == {
        "thinking": {"type": "enabled", "budget_tokens": 16000},
    }


async def test_litellm_gemini_budget_forwards_only_thinking_payload(monkeypatch) -> None:
    """Budget-based Gemini variants should not also send LiteLLM reasoning_effort."""
    pytest.importorskip("agents")
    litellm = pytest.importorskip("litellm")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel
    from agents.models.interface import ModelTracing

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model=LitellmModel(model="google/gemini-2.5-pro"))
    agency = type("Agency", (), {"agents": {"A": agent}})()
    seen: dict[str, object] = {}

    async def capture(**kwargs):
        seen.update(kwargs)
        msg = litellm.types.utils.Message(content="ok", role="assistant")
        choice = litellm.types.utils.Choices(finish_reason="stop", index=0, message=msg)
        return litellm.types.utils.ModelResponse(choices=[choice], model=kwargs["model"])

    monkeypatch.setattr(litellm, "acompletion", capture)

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="litellm/google/gemini-2.5-pro",
            model_settings_extra_args={
                "thinkingConfig": {"includeThoughts": True, "thinkingBudget": 16000},
                "reasoning_effort": "high",
            },
        ),
    )

    assert isinstance(agent.model, LitellmModel)
    assert agent.model_settings.reasoning is None
    assert agent.model_settings.extra_args == {"thinking": {"type": "enabled", "budget_tokens": 16000}}

    await agent.model._fetch_response(
        None,
        "hi",
        agent.model_settings,
        [],
        None,
        [],
        None,
        ModelTracing.DISABLED,
        stream=False,
    )

    assert seen["thinking"] == {"type": "enabled", "budget_tokens": 16000}
    assert seen["reasoning_effort"] is None


async def test_litellm_anthropic_budget_variant_preserves_reasoning_for_tool_replay(monkeypatch) -> None:
    """Anthropic budget-only thinking variants should replay signed thinking blocks across tool calls."""
    pytest.importorskip("agents")
    litellm = pytest.importorskip("litellm")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel
    from agents.models.interface import ModelTracing

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model=LitellmModel(model="anthropic/claude-sonnet-4-6"))
    agency = type("Agency", (), {"agents": {"A": agent}})()
    seen: dict[str, object] = {}

    async def capture(**kwargs):
        seen.update(kwargs)
        msg = litellm.types.utils.Message(content="ok", role="assistant")
        choice = litellm.types.utils.Choices(finish_reason="stop", index=0, message=msg)
        return litellm.types.utils.ModelResponse(choices=[choice], model=kwargs["model"])

    monkeypatch.setattr(litellm, "acompletion", capture)

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="litellm/anthropic/claude-sonnet-4-6",
            model_settings_extra_args={
                "thinking": {"type": "enabled", "budgetTokens": 16000},
            },
        ),
    )

    assert isinstance(agent.model, LitellmModel)
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "high"
    assert agent.model_settings.extra_args == {"thinking": {"type": "enabled", "budget_tokens": 16000}}

    await agent.model._fetch_response(
        None,
        [
            {
                "type": "reasoning",
                "id": "rs_1",
                "content": [{"type": "reasoning_text", "text": "private chain"}],
                "encrypted_content": "signed-thinking",
                "provider_data": {"model": "anthropic/claude-sonnet-4-6"},
            },
            {
                "type": "function_call",
                "id": "fc_1",
                "call_id": "call_1",
                "name": "lookup",
                "arguments": "{}",
                "provider_data": {"model": "anthropic/claude-sonnet-4-6"},
            },
            {"type": "function_call_output", "call_id": "call_1", "output": "tool result"},
        ],
        agent.model_settings,
        [],
        None,
        [],
        None,
        ModelTracing.DISABLED,
        stream=False,
    )

    assert seen["reasoning_effort"] == "high"
    assert seen["thinking"] == {"type": "enabled", "budget_tokens": 16000}
    messages = seen["messages"]
    assert isinstance(messages, list)
    assistant = messages[0]
    assert isinstance(assistant, dict)
    assert assistant["role"] == "assistant"
    assert assistant["content"] == [{"type": "thinking", "thinking": "private chain", "signature": "signed-thinking"}]
    assert assistant["tool_calls"][0]["id"] == "call_1"


def test_litellm_gemini_variant_maps_top_level_thinking_level() -> None:
    """Gemini 3 UI variants may arrive as top-level thinkingLevel/includeThoughts."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model=LitellmModel(model="google/gemini-3.5-flash"))
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="litellm/google/gemini-3.5-flash",
            model_settings_extra_args={
                "includeThoughts": True,
                "thinkingLevel": "high",
            },
        ),
    )

    assert isinstance(agent.model, LitellmModel)
    assert agent.model.model == "gemini/gemini-3.5-flash"
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "high"
    assert agent.model_settings.reasoning.summary is None
    assert agent.model_settings.extra_args is None


def test_openai_model_override_applies_explicit_variant_reasoning() -> None:
    """OpenAI variant effort should become request-scoped reasoning only when selected."""
    pytest.importorskip("agents")

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model="gpt-4o-mini")
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="gpt-5",
            model_settings_extra_args={"reasoning_effort": "high", "reasoning_summary": "auto"},
        ),
    )

    assert agent.model == "gpt-5"
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "high"
    assert agent.model_settings.reasoning.summary == "auto"
    assert agent.model_settings.extra_args is None


def test_openai_model_override_applies_summary_without_effort() -> None:
    """OpenAI summary-only variants should not forward raw reasoning_summary."""
    pytest.importorskip("agents")

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    control = Agent(name="A", instructions="x", model="gpt-4o-mini")
    control_agency = type("Agency", (), {"agents": {"A": control}})()
    apply_openai_client_config(control_agency, ClientConfig(model="gpt-5"))
    default_effort = control.model_settings.reasoning.effort if control.model_settings.reasoning is not None else None

    agent = Agent(name="A", instructions="x", model="gpt-4o-mini")
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="gpt-5",
            model_settings_extra_args={"reasoning_summary": "auto"},
        ),
    )

    assert agent.model == "gpt-5"
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == default_effort
    assert agent.model_settings.reasoning.summary == "auto"
    assert agent.model_settings.extra_args is None


def test_litellm_extra_arg_reasoning_effort_clears_stale_reasoning() -> None:
    """LiteLLM extra-arg providers should not keep stale template reasoning."""
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents import ModelSettings
    from agents.extensions.models.litellm_model import LitellmModel
    from openai.types.shared import Reasoning

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(
        name="A",
        instructions="x",
        model=LitellmModel(model="xai/grok-code-fast"),
        model_settings=ModelSettings(reasoning=Reasoning(effort="low")),
    )
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(model_settings_extra_args={"reasoning_effort": "high"}),
    )

    assert agent.model_settings.reasoning is None
    assert agent.model_settings.extra_args == {"reasoning_effort": "high"}


def test_gateway_provider_model_override_moves_provider_variant_args_to_extra_body() -> None:
    """Gateway-routed provider models should not leak provider args as OpenAI kwargs."""
    pytest.importorskip("agents")

    from agents import OpenAIResponsesModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model="gpt-4o-mini")
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="anthropic/claude-sonnet-4-6",
            api_key="sk-gateway",
            base_url="https://gateway.example/v1",
            model_settings_extra_args={
                "include": ["reasoning.encrypted_content"],
                "thinking": {"type": "enabled", "budgetTokens": 16000},
                "effort": "high",
            },
        ),
    )

    assert isinstance(agent.model, OpenAIResponsesModel)
    assert isinstance(agent.model._client, AsyncOpenAI)
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "high"
    assert agent.model_settings.response_include is None
    assert agent.model_settings.extra_body == {"thinking": {"type": "enabled", "budget_tokens": 16000}}
    assert agent.model_settings.extra_args is None


def test_openai_model_override_maps_variant_include_to_response_include() -> None:
    """OpenAI Responses variants should use typed include instead of duplicate extra args."""
    pytest.importorskip("agents")

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model="gpt-4o-mini")
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="gpt-5",
            model_settings_extra_args={
                "reasoning_effort": "medium",
                "reasoning_summary": "auto",
                "include": ["reasoning.encrypted_content"],
            },
        ),
    )

    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "medium"
    assert agent.model_settings.response_include == ["reasoning.encrypted_content"]
    assert agent.model_settings.extra_args is None


def test_model_settings_extra_args_apply_openrouter_extra_body_and_max_tokens() -> None:
    """OpenRouter options should reach typed ModelSettings fields, not extra_args."""
    pytest.importorskip("agents")

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model="gpt-4o-mini")
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model_settings_extra_args={
                "extra_body": {"reasoning": {"effort": "high"}},
                "max_tokens": 2500,
            },
        ),
    )

    assert agent.model_settings.extra_body == {"reasoning": {"effort": "high"}}
    assert agent.model_settings.max_tokens == 2500
    assert agent.model_settings.extra_args is None


@pytest.mark.parametrize("model_name", ["litellm/openai/gpt-5.4", "litellm/gpt-5"])
def test_litellm_openai_variant_sets_reasoning_without_forcing_other_providers(model_name: str) -> None:
    """OpenAI LiteLLM variants should enable Agents reasoning state only from explicit UI settings."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model=LitellmModel(model="openai/gpt-4o-mini"))
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model=model_name,
            model_settings_extra_args={"reasoning_effort": "high", "reasoning_summary": "auto"},
        ),
    )

    assert isinstance(agent.model, LitellmModel)
    assert agent.model_settings.reasoning is None
    assert agent.model_settings.extra_args == {"reasoning_effort": {"effort": "high", "summary": "auto"}}


@pytest.mark.parametrize("model_name", ["litellm/openai/gpt-5.4", "litellm/gpt-5"])
async def test_litellm_openai_variant_forwards_reasoning_summary_to_litellm(monkeypatch, model_name: str) -> None:
    """OpenAI LiteLLM summaries must reach the SDK chat-completions call payload."""
    pytest.importorskip("agents")
    litellm = pytest.importorskip("litellm")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel
    from agents.models.interface import ModelTracing

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model=LitellmModel(model="openai/gpt-4o-mini"))
    agency = type("Agency", (), {"agents": {"A": agent}})()
    seen: dict[str, object] = {}

    async def capture(**kwargs):
        seen.update(kwargs)
        msg = litellm.types.utils.Message(content="ok", role="assistant")
        choice = litellm.types.utils.Choices(finish_reason="stop", index=0, message=msg)
        return litellm.types.utils.ModelResponse(choices=[choice], model=kwargs["model"])

    monkeypatch.setattr(litellm, "acompletion", capture)

    apply_openai_client_config(
        agency,
        ClientConfig(
            model=model_name,
            model_settings_extra_args={"reasoning_effort": "high", "reasoning_summary": "auto"},
        ),
    )

    assert isinstance(agent.model, LitellmModel)
    await agent.model._fetch_response(
        None,
        "hi",
        agent.model_settings,
        [],
        None,
        [],
        None,
        ModelTracing.DISABLED,
        stream=False,
    )

    assert seen["reasoning_effort"] == {"effort": "high", "summary": "auto"}
    assert "reasoning_summary" not in seen


def test_litellm_prefixed_string_model_normalizes_variant_extra_args_without_model_override() -> None:
    """Existing LiteLLM-prefixed string models should still get provider-specific variant mapping."""
    pytest.importorskip("agents")

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model="litellm/anthropic/claude-sonnet-4-6")
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(model_settings_extra_args={"effort": "high", "reasoning_summary": "auto"}),
    )

    assert agent.model == "litellm/anthropic/claude-sonnet-4-6"
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "high"
    assert agent.model_settings.extra_args == {"reasoning_effort": "high"}


def test_litellm_prefixed_wrapper_model_normalizes_variant_extra_args_without_model_override() -> None:
    """Existing LiteLLM wrappers with a prefixed model should still get provider-specific variant mapping."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model=LitellmModel(model="litellm/anthropic/claude-sonnet-4-6"))
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(model_settings_extra_args={"effort": "high", "reasoning_summary": "auto"}),
    )

    assert isinstance(agent.model, LitellmModel)
    assert agent.model.model == "litellm/anthropic/claude-sonnet-4-6"
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "high"
    assert agent.model_settings.extra_args == {"reasoning_effort": "high"}


@pytest.mark.parametrize("model_name", ["xai/grok-4.3", "xai/grok-4-1-fast", "xai/grok-code-fast"])
def test_xai_grok_variant_forwards_selected_reasoning_effort(model_name: str) -> None:
    """Selected xAI Grok variants should reach LiteLLM as explicit extra args."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model=LitellmModel(model=model_name))
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model=f"litellm/{model_name}",
            model_settings_extra_args={
                "effort": "medium",
                "reasoning_effort": "high",
                "reasoning_summary": "auto",
                "include": ["reasoning.encrypted_content"],
            },
        ),
    )

    assert agent.model_settings.reasoning is None
    assert agent.model_settings.extra_args == {"reasoning_effort": "high"}


@pytest.mark.parametrize("model_name", ["xai/grok-4", "xai/grok-4-1-fast-non-reasoning"])
def test_xai_grok_variant_drops_unsupported_reasoning_effort(model_name: str) -> None:
    """xAI Grok variants without configurable reasoning should not receive LiteLLM reasoning args."""
    pytest.importorskip("agents")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model=LitellmModel(model=model_name))
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model=f"litellm/{model_name}",
            model_settings_extra_args={
                "effort": "medium",
                "reasoning_effort": "high",
                "reasoning_summary": "auto",
                "include": ["reasoning.encrypted_content"],
            },
        ),
    )

    assert agent.model_settings.reasoning is None
    assert agent.model_settings.extra_args is None


@pytest.mark.parametrize("model_name", ["xai/grok-4-1-fast", "xai/grok-code-fast"])
def test_xai_grok_fallback_keeps_configurable_reasoning_effort(monkeypatch, model_name: str) -> None:
    """If LiteLLM metadata is unavailable, configurable Grok variants should keep effort."""
    pytest.importorskip("agents")
    litellm = pytest.importorskip("litellm")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    def fail_supports_reasoning(*args, **kwargs):
        raise RuntimeError("metadata unavailable")

    monkeypatch.setattr(litellm, "supports_reasoning", fail_supports_reasoning)

    agent = Agent(name="A", instructions="x", model=LitellmModel(model=model_name))
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model=f"litellm/{model_name}",
            model_settings_extra_args={"reasoning_effort": "high", "reasoning_summary": "auto"},
        ),
    )

    assert agent.model_settings.reasoning is None
    assert agent.model_settings.extra_args == {"reasoning_effort": "high"}


def test_xai_grok_fallback_drops_fixed_reasoning_effort(monkeypatch) -> None:
    """If LiteLLM metadata is unavailable, fixed-reasoning Grok variants should stay stripped."""
    pytest.importorskip("agents")
    litellm = pytest.importorskip("litellm")
    pytest.importorskip("agents.extensions.models.litellm_model")

    from agents.extensions.models.litellm_model import LitellmModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    def fail_supports_reasoning(*args, **kwargs):
        raise RuntimeError("metadata unavailable")

    monkeypatch.setattr(litellm, "supports_reasoning", fail_supports_reasoning)

    agent = Agent(name="A", instructions="x", model=LitellmModel(model="xai/grok-4-fast-reasoning"))
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="litellm/xai/grok-4-fast-reasoning",
            model_settings_extra_args={"reasoning_effort": "high", "reasoning_summary": "auto"},
        ),
    )

    assert agent.model_settings.reasoning is None
    assert agent.model_settings.extra_args is None


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


def test_provider_path_model_override_routes_request_gateway_client() -> None:
    """Provider-prefixed request model must still flow through the request gateway client."""
    pytest.importorskip("agents")

    from agents import OpenAIResponsesModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    embedded = AsyncOpenAI(api_key="sk-agent", base_url="https://api.agent.test/v1")
    agent = Agent(name="A", instructions="x", model=OpenAIResponsesModel(model="gpt-4o", openai_client=embedded))
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="anthropic/claude-sonnet-4",
            base_url="https://gateway.test/v1",
            api_key="sk-gateway",
        ),
    )

    assert isinstance(agent.model, OpenAIResponsesModel)
    assert agent.model.model == "anthropic/claude-sonnet-4"
    # The embedded client must be replaced by the request-scoped gateway client.
    assert agent.model._client is not embedded
    assert agent.model._client.api_key == "sk-gateway"
    assert str(agent.model._client.base_url).startswith("https://gateway.test")


def test_openrouter_model_override_routes_to_openrouter_client() -> None:
    """OpenRouter request models must not send the OpenRouter key to OpenAI."""
    pytest.importorskip("agents")

    from agents import OpenAIChatCompletionsModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.openrouter import get_openrouter_model_name

    agent = Agent(name="A", instructions="x", model="gpt-4o-mini")
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="openrouter/anthropic/claude-sonnet-4.5",
            api_key="sk-openrouter",
        ),
    )

    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    assert agent.model.model == "anthropic/claude-sonnet-4.5"
    assert get_openrouter_model_name(agent.model) == "openrouter/anthropic/claude-sonnet-4.5"
    assert agent.model._client.api_key == "sk-openrouter"
    assert str(agent.model._client.base_url).startswith("https://openrouter.ai/api/v1")


def test_openrouter_model_override_keeps_attachment_clients_on_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenRouter chat routing must not move direct file lookup clients to OpenRouter."""
    pytest.importorskip("agents")

    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.openrouter import get_openrouter_model_name

    openai_client = AsyncOpenAI(api_key="sk-openai", base_url="https://api.openai.com/v1")
    monkeypatch.setattr(endpoint_handlers, "get_default_openai_client", lambda: openai_client)

    agent = Agent(name="A", instructions="x", model="gpt-4o-mini")
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(model="openrouter/anthropic/claude-sonnet-4.5", api_key="sk-openrouter"),
    )

    assert get_openrouter_model_name(agent.model) == "openrouter/anthropic/claude-sonnet-4.5"
    assert agent.model._client.api_key == "sk-openrouter"
    assert str(agent.model._client.base_url).startswith("https://openrouter.ai/api/v1")
    assert agent._openai_client is openai_client
    assert str(agent._openai_client_sync.base_url).startswith("https://api.openai.com/v1")


def test_configured_openrouter_request_keeps_attachment_clients_on_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured OpenRouter agents should not use OpenRouter for direct file lookup clients."""
    pytest.importorskip("agents")

    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.openrouter import get_openrouter_model_name

    openai_client = AsyncOpenAI(api_key="sk-openai", base_url="https://api.openai.com/v1")
    monkeypatch.setattr(endpoint_handlers, "get_default_openai_client", lambda: openai_client)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-existing-openrouter")

    agent = Agent(name="A", instructions="x", model="openrouter/anthropic/claude-sonnet-4.5")
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(api_key="sk-openrouter"))

    assert get_openrouter_model_name(agent.model) == "openrouter/anthropic/claude-sonnet-4.5"
    assert agent.model._client.api_key == "sk-openrouter"
    assert str(agent.model._client.base_url).startswith("https://openrouter.ai/api/v1")
    assert agent._openai_client is openai_client
    assert str(agent._openai_client_sync.base_url).startswith("https://api.openai.com/v1")


def test_configured_openrouter_request_preserves_cached_attachment_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenRouter request routing should not replace an agent file client with the global default."""
    pytest.importorskip("agents")

    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.openrouter import get_openrouter_model_name

    default = AsyncOpenAI(api_key="sk-default", base_url="https://api.default.test/v1")
    file_client = AsyncOpenAI(api_key="sk-agent-files", base_url="https://api.agent-files.test/v1")
    monkeypatch.setattr(endpoint_handlers, "get_default_openai_client", lambda: default)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-existing-openrouter")

    agent = Agent(name="A", instructions="x", model="openrouter/anthropic/claude-sonnet-4.5")
    agent._openai_client = file_client
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(api_key="sk-openrouter"))

    assert get_openrouter_model_name(agent.model) == "openrouter/anthropic/claude-sonnet-4.5"
    assert agent.model._client.api_key == "sk-openrouter"
    assert str(agent.model._client.base_url).startswith("https://openrouter.ai/api/v1")
    assert agent._openai_client is file_client
    assert agent._openai_client is not default
    assert str(agent._openai_client_sync.base_url).startswith("https://api.agent-files.test/v1")


def test_openrouter_model_override_uses_request_base_url() -> None:
    """OpenRouter request models should honor request-scoped gateway base_url."""
    pytest.importorskip("agents")

    from agents import OpenAIChatCompletionsModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model="gpt-4o-mini")
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="openrouter/anthropic/claude-sonnet-4.5",
            base_url="https://openrouter-proxy.test/v1",
            api_key="sk-openrouter",
        ),
    )

    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    assert agent.model._client.api_key == "sk-openrouter"
    assert str(agent.model._client.base_url).startswith("https://openrouter-proxy.test/v1")


def test_openrouter_model_override_uses_env_key_with_request_base_url_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Base-url-only OpenRouter overrides should not require an OpenAI client."""
    pytest.importorskip("agents")

    from agents import OpenAIChatCompletionsModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter-env")
    monkeypatch.setattr(endpoint_handlers, "get_default_openai_client", lambda: None)

    agent = Agent(name="A", instructions="x", model="gpt-4o-mini")
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="openrouter/anthropic/claude-sonnet-4.5",
            base_url="https://openrouter-proxy.test/v1",
        ),
    )

    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    assert agent.model.model == "anthropic/claude-sonnet-4.5"
    assert agent.model._client.api_key == "sk-openrouter-env"
    assert str(agent.model._client.base_url).startswith("https://openrouter-proxy.test/v1")


@pytest.mark.parametrize(
    ("config", "expected_api_key", "expected_base_url", "expected_headers"),
    [
        (ClientConfig(api_key="sk-request"), "sk-request", "https://openrouter.ai/api/v1", {}),
        (
            ClientConfig(base_url="https://openrouter-proxy.test/v1"),
            "sk-original",
            "https://openrouter-proxy.test/v1",
            {},
        ),
        (
            ClientConfig(default_headers={"x-request-id": "req-1"}),
            "sk-original",
            "https://openrouter.ai/api/v1",
            {"x-request-id": "req-1"},
        ),
    ],
)
def test_configured_openrouter_agent_applies_request_client_without_model_override(
    monkeypatch: pytest.MonkeyPatch,
    config: ClientConfig,
    expected_api_key: str,
    expected_base_url: str,
    expected_headers: dict[str, str],
) -> None:
    """Configured OpenRouter agents should honor request client overrides without config.model."""
    pytest.importorskip("agents")

    from agents import OpenAIChatCompletionsModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.utils.openrouter import get_openrouter_model_name

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-original")

    agent = Agent(name="A", instructions="x", model="openrouter/anthropic/claude-sonnet-4.5")
    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    original_client = agent.model._client
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, config)

    assert config.model is None
    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    assert agent.model.model == "anthropic/claude-sonnet-4.5"
    assert get_openrouter_model_name(agent.model) == "openrouter/anthropic/claude-sonnet-4.5"
    assert agent.model._client is not original_client
    assert agent.model._client.api_key == expected_api_key
    assert str(agent.model._client.base_url).startswith(expected_base_url)
    headers = dict(agent.model._client.default_headers or {})
    for key, value in expected_headers.items():
        assert headers[key] == value


def test_configured_openrouter_model_override_preserves_injected_client_without_env_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenRouter model swaps should reuse the configured client when no client override is requested."""
    pytest.importorskip("agents")

    from agents import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.openrouter import build_openrouter_chat_model, get_openrouter_model_name

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = AsyncOpenAI(
        api_key="sk-injected",
        base_url="https://openrouter-proxy.test/v1",
        default_headers={"x-client": "kept"},
    )
    source = build_openrouter_chat_model(
        "openrouter/anthropic/claude-sonnet-4.5",
        openai_client=client,
    )
    agent = Agent(name="A", instructions="x", model=source)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="openrouter/openai/gpt-5"))

    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    assert agent.model.model == "openai/gpt-5"
    assert get_openrouter_model_name(agent.model) == "openrouter/openai/gpt-5"
    assert agent.model._client is client
    assert str(agent.model._client.base_url).startswith("https://openrouter-proxy.test/v1")
    assert dict(agent.model._client.default_headers)["x-client"] == "kept"


def test_configured_openrouter_model_override_preserves_replay_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenRouter model swaps should keep custom reasoning replay policy."""
    pytest.importorskip("agents")

    from agents import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.openrouter import build_openrouter_chat_model

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = AsyncOpenAI(
        api_key="sk-injected",
        base_url="https://openrouter-proxy.test/v1",
    )

    def replay(_context):
        return False

    source = build_openrouter_chat_model(
        "openrouter/anthropic/claude-sonnet-4.5",
        openai_client=client,
        should_replay_reasoning_content=replay,
    )
    agent = Agent(name="A", instructions="x", model=source)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="openrouter/openai/gpt-5"))

    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    assert agent.model.should_replay_reasoning_content is replay


def test_openrouter_override_does_not_reuse_custom_gateway_source_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenRouter swaps should not send OpenRouter models to a custom gateway."""
    pytest.importorskip("agents")

    from agents import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.openrouter import get_openrouter_model_name

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter-env")
    client = AsyncOpenAI(
        api_key="sk-gateway",
        base_url="https://gateway.test/v1",
        default_headers={"x-source": "kept"},
    )

    def replay(_context):
        return False

    source = OpenAIChatCompletionsModel(
        model="gpt-4o-mini",
        openai_client=client,
        should_replay_reasoning_content=replay,
    )
    agent = Agent(name="A", instructions="x", model=source)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="openrouter/anthropic/claude-sonnet-4.5"))

    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    assert agent.model.model == "anthropic/claude-sonnet-4.5"
    assert get_openrouter_model_name(agent.model) == "openrouter/anthropic/claude-sonnet-4.5"
    assert agent.model._client is not client
    assert agent.model._client.api_key == "sk-openrouter-env"
    assert str(agent.model._client.base_url).startswith("https://openrouter.ai/api/v1")
    assert agent.model.should_replay_reasoning_content is replay


def test_openrouter_override_preserves_official_source_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenRouter swaps should keep headers, not OpenAI auth, from official-base wrappers."""
    pytest.importorskip("agents")

    from agents import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.openrouter import get_openrouter_model_name

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter-env")
    client = AsyncOpenAI(
        api_key="sk-source",
        base_url="https://api.openai.com/v1",
        default_headers={"x-source": "kept"},
        timeout=12,
        max_retries=3,
    )

    def replay(_context):
        return False

    source = OpenAIChatCompletionsModel(
        model="gpt-4o-mini",
        openai_client=client,
        should_replay_reasoning_content=replay,
    )
    agent = Agent(name="A", instructions="x", model=source)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="openrouter/anthropic/claude-sonnet-4.5"))

    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    assert agent.model.model == "anthropic/claude-sonnet-4.5"
    assert get_openrouter_model_name(agent.model) == "openrouter/anthropic/claude-sonnet-4.5"
    assert agent.model._client is not client
    assert agent.model._client.api_key == "sk-openrouter-env"
    assert str(agent.model._client.base_url).startswith("https://openrouter.ai/api/v1")
    assert agent.model._client.timeout == 12
    assert agent.model._client.max_retries == 3
    assert dict(agent.model._client.default_headers)["x-source"] == "kept"
    assert agent.model.should_replay_reasoning_content is replay


def test_openrouter_override_request_key_copies_official_source_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Request OpenRouter credentials should copy source client settings."""
    pytest.importorskip("agents")

    from agents import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = AsyncOpenAI(
        api_key="sk-source",
        base_url="https://api.openai.com/v1",
        default_headers={"x-source": "old"},
        timeout=12,
        max_retries=3,
    )
    source = OpenAIChatCompletionsModel(model="gpt-4o-mini", openai_client=client)
    agent = Agent(name="A", instructions="x", model=source)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="openrouter/anthropic/claude-sonnet-4.5",
            api_key="sk-openrouter-request",
            default_headers={"x-source": "new"},
        ),
    )

    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    assert agent.model._client is not client
    assert agent.model._client.api_key == "sk-openrouter-request"
    assert str(agent.model._client.base_url).startswith("https://openrouter.ai/api/v1")
    assert agent.model._client.timeout == 12
    assert agent.model._client.max_retries == 3
    assert dict(agent.model._client.default_headers)["x-source"] == "new"


def test_configured_openrouter_agent_openai_override_drops_openrouter_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI request model overrides from OpenRouter agents must leave the OpenRouter gateway."""
    pytest.importorskip("agents")

    from agents import OpenAIChatCompletionsModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.openrouter import get_openrouter_model_name

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter")

    agent = Agent(name="A", instructions="x", model="openrouter/anthropic/claude-sonnet-4.5")
    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    openrouter_client = agent.model._client
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="gpt-4o-mini", api_key="sk-openai"))

    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    assert agent.model.model == "gpt-4o-mini"
    assert get_openrouter_model_name(agent.model) is None
    assert agent.model._client is not openrouter_client
    assert agent.model._client.api_key == "sk-openai"
    assert not str(agent.model._client.base_url).startswith("https://openrouter.ai/api/v1")
    assert str(agent.model._client.base_url).startswith("https://api.openai.com/v1")


def test_openrouter_agent_provider_override_without_gateway_stays_unwrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider-prefixed overrides should not be sent through a default OpenAI client."""
    pytest.importorskip("agents")

    from agents import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    default = AsyncOpenAI(api_key="sk-default-openai", base_url="https://api.openai.com/v1")
    monkeypatch.setattr(endpoint_handlers, "get_default_openai_client", lambda: default)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter")

    agent = Agent(name="A", instructions="x", model="openrouter/anthropic/claude-sonnet-4.5")
    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="anthropic/claude-sonnet-4"))

    assert agent.model == "anthropic/claude-sonnet-4"


def test_openrouter_agent_provider_override_with_gateway_wraps_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit gateway base_url makes a provider-prefixed OpenAI wrapper intentional."""
    pytest.importorskip("agents")

    from agents import OpenAIChatCompletionsModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.openrouter import get_openrouter_model_name

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter")

    agent = Agent(name="A", instructions="x", model="openrouter/anthropic/claude-sonnet-4.5")
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="anthropic/claude-sonnet-4",
            base_url="https://gateway.test/v1",
            api_key="sk-gateway",
        ),
    )

    assert isinstance(agent.model, OpenAIChatCompletionsModel)
    assert get_openrouter_model_name(agent.model) is None
    assert agent.model.model == "anthropic/claude-sonnet-4"
    assert agent.model._client.api_key == "sk-gateway"
    assert str(agent.model._client.base_url).startswith("https://gateway.test")


def test_openrouter_helper_uses_injected_client_without_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Injected OpenAI-compatible clients should not need OPENROUTER_API_KEY."""
    pytest.importorskip("agents")

    from agents import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    from agency_swarm.utils.openrouter import build_openrouter_chat_model

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = AsyncOpenAI(api_key="sk-injected", base_url="https://openrouter-proxy.test/v1")

    model = build_openrouter_chat_model(
        "openrouter/anthropic/claude-sonnet-4.5",
        openai_client=client,
    )

    assert isinstance(model, OpenAIChatCompletionsModel)
    assert model._client is client
    assert model.model == "anthropic/claude-sonnet-4.5"


def test_openrouter_model_override_requires_api_key(monkeypatch) -> None:
    """OpenRouter overrides should fail explicitly when no key is available."""
    pytest.importorskip("agents")

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    agent = Agent(name="A", instructions="x", model="gpt-4o-mini")
    agency = type("Agency", (), {"agents": {"A": agent}})()

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY is required"):
        apply_openai_client_config(
            agency,
            ClientConfig(model="openrouter/anthropic/claude-sonnet-4.5"),
        )


def test_model_override_refreshes_gpt5_framework_defaults() -> None:
    """Swapping to a GPT-5 model should re-layer reasoning defaults without wiping headers."""
    pytest.importorskip("agents")

    from agents import ModelSettings

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model="gpt-4o-mini")
    agent.model_settings = ModelSettings(extra_headers={"x-caller": "1"})
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="gpt-5"))

    # Reasoning effort from the SDK GPT-5 defaults must reach the agent after the swap.
    assert agent.model == "gpt-5"
    assert agent.model_settings is not None
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "low"
    # Caller-set extra_headers must survive the refresh.
    assert agent.model_settings.extra_headers == {"x-caller": "1"}


def test_model_override_preserves_openclaw_usage_alias() -> None:
    """OpenClaw usage-name alias must survive a request model swap."""
    pytest.importorskip("agents")

    from agents import OpenAIResponsesModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.model_utils import get_usage_tracking_model_name

    embedded = AsyncOpenAI(api_key="sk-agent", base_url="https://openclaw.test/v1")
    source = OpenAIResponsesModel(model="openclaw:main", openai_client=embedded)
    source._agency_swarm_usage_model_name = "openai/gpt-5.4"  # type: ignore[attr-defined]
    agent = Agent(name="A", instructions="x", model=source)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="openclaw:main"))

    assert isinstance(agent.model, OpenAIResponsesModel)
    # Same name, new instance — the custom alias must carry over.
    assert get_usage_tracking_model_name(agent.model) == "openai/gpt-5.4"


def test_string_model_override_wraps_gateway_for_provider_prefix() -> None:
    """Bare-string agents whose request model is provider-prefixed must still bind the gateway client."""
    pytest.importorskip("agents")

    from agents import OpenAIResponsesModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(name="A", instructions="x", model="gpt-4o")
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(
        agency,
        ClientConfig(
            model="anthropic/claude-sonnet-4",
            base_url="https://gateway.test/v1",
            api_key="sk-gateway",
        ),
    )

    # The provider-prefixed name must route through the request-scoped gateway client,
    # not silently stay as a bare string (which would skip the override entirely).
    assert isinstance(agent.model, OpenAIResponsesModel)
    assert agent.model.model == "anthropic/claude-sonnet-4"
    assert agent.model._client.api_key == "sk-gateway"
    assert str(agent.model._client.base_url).startswith("https://gateway.test")


def test_model_override_does_not_stick_old_gpt5_reasoning_settings() -> None:
    """Swapping GPT-5 -> GPT-4o must recompute settings, not inherit GPT-5 reasoning."""
    pytest.importorskip("agents")

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    # Agent starts on gpt-5, which layers reasoning.effort="low" at construction.
    agent = Agent(name="A", instructions="x", model="gpt-5")
    assert agent.model_settings is not None
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "low"

    agency = type("Agency", (), {"agents": {"A": agent}})()
    apply_openai_client_config(agency, ClientConfig(model="gpt-4o"))

    # After swapping to gpt-4o, the old GPT-5 reasoning defaults must not stick.
    assert agent.model == "gpt-4o"
    assert agent.model_settings is not None
    assert agent.model_settings.reasoning is None


def test_model_override_carries_openclaw_default_settings_alias() -> None:
    """OpenClaw default-settings alias must survive a same-name request model swap."""
    pytest.importorskip("agents")

    from agents import OpenAIResponsesModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.model_utils import get_default_settings_model_name

    embedded = AsyncOpenAI(api_key="sk-agent", base_url="https://openclaw.test/v1")
    source = OpenAIResponsesModel(model="openclaw:main", openai_client=embedded)
    source._agency_swarm_default_model_name = "gpt-5"  # type: ignore[attr-defined]
    agent = Agent(name="A", instructions="x", model=source)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="openclaw:main"))

    assert isinstance(agent.model, OpenAIResponsesModel)
    # OpenClaw default-settings lookup relies on this alias being carried.
    assert get_default_settings_model_name(agent.model) == "gpt-5"


def test_model_override_drops_usage_alias_when_model_name_changes() -> None:
    """OpenClaw usage alias must NOT be copied when the swap changes the model name."""
    pytest.importorskip("agents")

    from agents import OpenAIResponsesModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.model_utils import get_usage_tracking_model_name

    embedded = AsyncOpenAI(api_key="sk-agent", base_url="https://openclaw.test/v1")
    source = OpenAIResponsesModel(model="openclaw:main", openai_client=embedded)
    source._agency_swarm_usage_model_name = "openai/gpt-5.4"  # type: ignore[attr-defined]
    agent = Agent(name="A", instructions="x", model=source)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    apply_openai_client_config(agency, ClientConfig(model="gpt-4.1"))

    assert isinstance(agent.model, OpenAIResponsesModel)
    assert agent.model.model == "gpt-4.1"
    # The alias belonged to openclaw:main — it must not inherit onto gpt-4.1.
    assert get_usage_tracking_model_name(agent.model) == "gpt-4.1"


def test_model_override_preserves_caller_generation_settings_on_gpt5_to_gpt4o_swap() -> None:
    """Caller-tuned generation settings must survive a GPT-5 -> GPT-4o swap."""
    pytest.importorskip("agents")

    from agents import ModelSettings

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    agent = Agent(
        name="A",
        instructions="x",
        model="gpt-5",
        model_settings=ModelSettings(temperature=0.7, max_tokens=123),
    )
    # Sanity-check pre-swap state: GPT-5 family defaults are layered on top.
    assert agent.model_settings.temperature == 0.7
    assert agent.model_settings.max_tokens == 123
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "low"

    agency = type("Agency", (), {"agents": {"A": agent}})()
    apply_openai_client_config(agency, ClientConfig(model="gpt-4o"))

    # After the swap the GPT-5 family defaults are gone, but caller-tuned
    # generation settings remain intact.
    assert agent.model == "gpt-4o"
    assert agent.model_settings.reasoning is None
    assert agent.model_settings.verbosity is None
    assert agent.model_settings.temperature == 0.7
    assert agent.model_settings.max_tokens == 123


def test_model_override_drops_openclaw_aliases_when_base_url_changes() -> None:
    """OpenClaw aliases must NOT be copied when the rebuild swaps the gateway base URL."""
    pytest.importorskip("agents")

    from agents import OpenAIResponsesModel
    from openai import AsyncOpenAI

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig
    from agency_swarm.utils.model_utils import get_default_settings_model_name, get_usage_tracking_model_name

    embedded = AsyncOpenAI(api_key="sk-agent", base_url="https://openclaw.test/v1")
    source = OpenAIResponsesModel(model="openclaw:main", openai_client=embedded)
    source._agency_swarm_default_model_name = "gpt-5"  # type: ignore[attr-defined]
    source._agency_swarm_usage_model_name = "openai/gpt-5.4"  # type: ignore[attr-defined]
    agent = Agent(name="A", instructions="x", model=source)
    agency = type("Agency", (), {"agents": {"A": agent}})()

    # Same model name, but base_url changes — the old OpenClaw registration is stale.
    apply_openai_client_config(
        agency,
        ClientConfig(model="openclaw:main", base_url="https://other-gateway.test/v1", api_key="sk-new"),
    )

    assert isinstance(agent.model, OpenAIResponsesModel)
    assert agent.model.model == "openclaw:main"
    # Both aliases must be dropped — the rebuilt wrapper is now pointing at a different gateway.
    assert get_default_settings_model_name(agent.model) == "openclaw:main"
    assert get_usage_tracking_model_name(agent.model) == "openclaw:main"

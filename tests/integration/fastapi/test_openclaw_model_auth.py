from __future__ import annotations

import pytest

from agency_swarm.integrations import openclaw as openclaw_mod
from agency_swarm.integrations.openclaw import build_openclaw_responses_model
from agency_swarm.utils.model_utils import get_default_settings_model_name, get_usage_tracking_model_name


def test_build_openclaw_responses_model_uses_app_token_when_proxy_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENCLAW_PROXY_API_KEY", raising=False)
    monkeypatch.setenv("APP_TOKEN", "app-token")

    model = build_openclaw_responses_model()

    assert model._client.api_key == "app-token"


def test_build_openclaw_responses_model_prefers_app_token_over_proxy_key_for_current_app_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_PROXY_API_KEY", "proxy-token")
    monkeypatch.setenv("APP_TOKEN", "app-token")

    model = build_openclaw_responses_model()

    assert model._client.api_key == "app-token"


def test_build_openclaw_responses_model_prefers_openclaw_proxy_key_for_external_proxy_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_PROXY_API_KEY", "proxy-token")
    monkeypatch.setenv("APP_TOKEN", "app-token")

    model = build_openclaw_responses_model(base_url="https://example.com/openclaw/v1")

    assert model._client.api_key == "proxy-token"


def test_build_openclaw_responses_model_uses_gateway_token_when_proxy_and_app_tokens_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENCLAW_PROXY_API_KEY", raising=False)
    monkeypatch.delenv("APP_TOKEN", raising=False)
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "gateway-token")

    model = build_openclaw_responses_model()

    assert model._client.api_key == "gateway-token"


def test_build_openclaw_responses_model_uses_gateway_token_before_app_token_for_direct_gateway_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_PROXY_API_KEY", "proxy-token")
    monkeypatch.setenv("APP_TOKEN", "app-token")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "gateway-token")

    model = build_openclaw_responses_model(base_url="http://127.0.0.1:18789/v1")

    assert model._client.api_key == "gateway-token"


def test_build_openclaw_responses_model_uses_openclaw_default_model_env_when_model_unspecified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENCLAW_PROXY_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_HOST", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setenv("OPENCLAW_DEFAULT_MODEL", "openclaw:beta")
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)

    model = build_openclaw_responses_model()

    assert model.model == "openclaw:beta"


def test_build_openclaw_responses_model_ignores_openclaw_alias_defaults_for_direct_gateway_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_DEFAULT_MODEL", "openclaw:main")
    monkeypatch.setenv("OPENCLAW_PROVIDER_MODEL", "anthropic/claude-sonnet-4-5")

    model = build_openclaw_responses_model(base_url="http://127.0.0.1:18789/v1", api_key="external-token")

    assert model.model == "anthropic/claude-sonnet-4-5"


def test_build_openclaw_responses_model_defaults_external_v1_to_provider_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_PROVIDER_MODEL", "anthropic/claude-sonnet-4-5")

    model = build_openclaw_responses_model(base_url="http://127.0.0.1:18789/v1", api_key="external-token")

    assert model.model == "anthropic/claude-sonnet-4-5"


def test_build_openclaw_responses_model_preserves_openclaw_aliases_for_direct_gateway_urls() -> None:
    model = build_openclaw_responses_model(
        model="openclaw:custom",
        base_url="http://127.0.0.1:18789/v1",
        api_key="external-token",
    )

    assert model.model == "openclaw:custom"
    assert get_usage_tracking_model_name(model) == "openclaw:custom"
    assert get_default_settings_model_name(model) == "openclaw:custom"


def test_build_openclaw_responses_model_preserves_explicit_nondefault_alias_metadata_for_current_app_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULT_PATTERNS", [], raising=False)
    openclaw_mod.openclaw_model.register_current_app_openclaw_defaults(
        default_model="openclaw:main",
        provider_model="openai/gpt-5.4-mini",
        base_url="https://app.example/openclaw/v1",
    )

    model = build_openclaw_responses_model(
        model="openclaw:alt",
        base_url="https://app.example/openclaw/v1",
        api_key="app-token",
    )

    assert model.model == "openclaw:alt"
    assert get_usage_tracking_model_name(model) == "openclaw:alt"
    assert get_default_settings_model_name(model) == "openclaw:alt"

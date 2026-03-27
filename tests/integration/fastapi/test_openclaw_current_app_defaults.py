from __future__ import annotations

import gc
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("fastapi.testclient")
from fastapi import FastAPI

from agency_swarm.integrations import openclaw as openclaw_mod
from agency_swarm.integrations.openclaw import attach_openclaw_to_fastapi, build_openclaw_responses_model
from agency_swarm.utils.model_utils import get_usage_tracking_model_name
from tests.integration.fastapi._openclaw_test_support import _build_openclaw_config


def test_build_openclaw_responses_model_uses_programmatic_current_app_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENCLAW_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROVIDER_MODEL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_HOST", raising=False)
    monkeypatch.setenv("OPENCLAW_PROXY_PORT", "8000")
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)

    app = FastAPI()
    config = replace(
        _build_openclaw_config(tmp_path),
        default_model="openclaw:custom",
        provider_model="anthropic/claude-sonnet-4-5",
    )
    attach_openclaw_to_fastapi(app, config)

    model = build_openclaw_responses_model(base_url="http://127.0.0.1:8000/openclaw/v1", api_key="app-token")

    assert model.model == "openclaw:custom"
    assert get_usage_tracking_model_name(model) == "anthropic/claude-sonnet-4-5"


def test_build_openclaw_responses_model_uses_programmatic_current_app_defaults_for_proxy_host_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENCLAW_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROVIDER_MODEL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_BASE_URL", raising=False)
    monkeypatch.setenv("OPENCLAW_PROXY_HOST", "proxy.internal")
    monkeypatch.delenv("OPENCLAW_PROXY_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)

    app = FastAPI()
    config = replace(
        _build_openclaw_config(tmp_path),
        default_model="openclaw:custom",
        provider_model="anthropic/claude-sonnet-4-5",
    )
    attach_openclaw_to_fastapi(app, config)

    model = build_openclaw_responses_model(base_url="http://proxy.internal:8000/openclaw/v1", api_key="app-token")

    assert model.model == "openclaw:custom"
    assert get_usage_tracking_model_name(model) == "anthropic/claude-sonnet-4-5"


def test_build_openclaw_responses_model_uses_app_token_and_defaults_for_explicit_same_app_proxy_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENCLAW_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROVIDER_MODEL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_HOST", raising=False)
    monkeypatch.setenv("OPENCLAW_PROXY_PORT", "9000")
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setenv("APP_TOKEN", "app-token")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "gateway-token")
    monkeypatch.setenv("OPENCLAW_PROXY_API_KEY", "proxy-token")
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)

    app = FastAPI()
    config = replace(
        _build_openclaw_config(tmp_path),
        port=9000,
        default_model="openclaw:custom",
        provider_model="openai/gpt-4o",
    )
    attach_openclaw_to_fastapi(app, config)

    model = build_openclaw_responses_model(base_url="http://127.0.0.1:9000/openclaw/v1")

    assert model.model == "openclaw:custom"
    assert get_usage_tracking_model_name(model) == "openai/gpt-4o"
    assert model._client.api_key == "app-token"


@pytest.mark.parametrize(
    ("server_url", "base_url"),
    [
        ("http://localhost:9000", "http://127.0.0.1:9000/openclaw/v1"),
        ("https://example.com/{stage}", "https://example.com/prod/openclaw/v1"),
    ],
)
def test_attach_openclaw_to_fastapi_uses_app_server_url_for_same_app_proxy_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, server_url: str, base_url: str
) -> None:
    monkeypatch.delenv("OPENCLAW_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROVIDER_MODEL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_HOST", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setenv("APP_TOKEN", "app-token")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "gateway-token")
    monkeypatch.setenv("OPENCLAW_PROXY_API_KEY", "proxy-token")
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULT_PATTERNS", [], raising=False)

    app = FastAPI(servers=[{"url": server_url}])
    config = replace(
        _build_openclaw_config(tmp_path),
        default_model="openclaw:custom",
        provider_model="anthropic/claude-sonnet-4-5",
    )
    attach_openclaw_to_fastapi(app, config)

    model = build_openclaw_responses_model(base_url=base_url)

    assert model.model == "openclaw:custom"
    assert get_usage_tracking_model_name(model) == "anthropic/claude-sonnet-4-5"
    assert model._client.api_key == "app-token"


def test_attach_openclaw_to_fastapi_does_not_trust_relative_server_urls_as_current_app_proxy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENCLAW_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROVIDER_MODEL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_HOST", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setenv("APP_TOKEN", "app-token")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "gateway-token")
    monkeypatch.setenv("OPENCLAW_PROXY_API_KEY", "proxy-token")
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULT_PATTERNS", [], raising=False)

    app = FastAPI(servers=[{"url": "/api"}])
    config = replace(
        _build_openclaw_config(tmp_path),
        default_model="openclaw:custom",
        provider_model="anthropic/claude-sonnet-4-5",
    )
    attach_openclaw_to_fastapi(app, config)

    model = build_openclaw_responses_model(base_url="https://example.com/api/openclaw/v1")

    assert model.model == "openclaw:main"
    assert get_usage_tracking_model_name(model) == "openclaw:main"
    assert model._client.api_key == "proxy-token"


def test_attach_openclaw_to_fastapi_does_not_register_gateway_port_as_proxy_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENCLAW_DEFAULT_MODEL", raising=False)
    monkeypatch.setenv("OPENCLAW_PROVIDER_MODEL", "openai/gpt-5.4-mini")
    monkeypatch.delenv("OPENCLAW_PROXY_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_HOST", raising=False)
    monkeypatch.setenv("OPENCLAW_PROXY_PORT", "8000")
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setenv("APP_TOKEN", "app-token")
    monkeypatch.setenv("OPENCLAW_PROXY_API_KEY", "proxy-token")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "gateway-token")
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)

    attach_openclaw_to_fastapi(FastAPI(), replace(_build_openclaw_config(tmp_path), port=9000))

    model = build_openclaw_responses_model(base_url="http://127.0.0.1:9000/openclaw/v1")

    assert model.model == "openclaw:main"
    assert get_usage_tracking_model_name(model) == "openclaw:main"
    assert model._client.api_key == "proxy-token"


def test_attach_openclaw_to_fastapi_rejects_conflicting_current_app_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENCLAW_PROXY_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_HOST", raising=False)
    monkeypatch.setenv("OPENCLAW_PROXY_PORT", "8000")
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)

    first_config = replace(
        _build_openclaw_config(tmp_path / "first"),
        default_model="openclaw:first",
        provider_model="openai/gpt-4o",
    )
    second_config = replace(
        _build_openclaw_config(tmp_path / "second"),
        default_model="openclaw:second",
        provider_model="openai/gpt-5.4-mini",
    )

    attach_openclaw_to_fastapi(FastAPI(), first_config)

    with pytest.raises(ValueError, match="Conflicting current-app OpenClaw defaults"):
        attach_openclaw_to_fastapi(FastAPI(), second_config)


def test_attach_openclaw_to_fastapi_rolls_back_defaults_on_partial_registration_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """P1-a: earlier URLs are cleaned up when a later registration fails."""
    monkeypatch.delenv("OPENCLAW_PROXY_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_HOST", raising=False)
    monkeypatch.setenv("OPENCLAW_PROXY_PORT", "9000")
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULT_COUNTS", {}, raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULT_PATTERNS", [], raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULT_PATTERN_COUNTS", {}, raising=False)

    # Pre-register a conflicting entry for the server URL so the second
    # registration in the loop raises ValueError.
    conflict_url = "https://conflict.example/openclaw/v1"
    openclaw_mod.openclaw_model.register_current_app_openclaw_defaults(
        default_model="openclaw:existing",
        provider_model="openai/gpt-4o",
        base_url=conflict_url,
    )

    app = FastAPI(servers=[{"url": "https://conflict.example"}])
    config = replace(
        _build_openclaw_config(tmp_path),
        default_model="openclaw:new",
        provider_model="openai/gpt-5.4-mini",
    )

    with pytest.raises(ValueError, match="Conflicting"):
        attach_openclaw_to_fastapi(app, config)

    # The first URL (http://127.0.0.1:9000/openclaw/v1) should have been
    # rolled back.  Only the pre-registered conflict entry should remain.
    default_url_key = openclaw_mod.openclaw_model._normalize_openclaw_proxy_url("http://127.0.0.1:9000/openclaw/v1")
    assert default_url_key not in openclaw_mod.openclaw_model._CURRENT_APP_OPENCLAW_DEFAULTS
    assert default_url_key not in openclaw_mod.openclaw_model._CURRENT_APP_OPENCLAW_DEFAULT_COUNTS


def test_attach_openclaw_to_fastapi_distinct_apps_coexist_without_explicit_proxy_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """P1-b: two apps with different defaults coexist when OPENCLAW_PROXY_PORT is unset."""
    monkeypatch.delenv("OPENCLAW_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROVIDER_MODEL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_HOST", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULT_COUNTS", {}, raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULT_PATTERNS", [], raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULT_PATTERN_COUNTS", {}, raising=False)

    first_config = replace(
        _build_openclaw_config(tmp_path / "first"),
        default_model="openclaw:first",
        provider_model="openai/gpt-4o",
    )
    second_config = replace(
        _build_openclaw_config(tmp_path / "second"),
        default_model="openclaw:second",
        provider_model="openai/gpt-5.4-mini",
    )

    app1 = FastAPI()
    app2 = FastAPI()

    # Both should succeed — no ValueError.
    attach_openclaw_to_fastapi(app1, first_config)
    attach_openclaw_to_fastapi(app2, second_config)

    # Synthetic loopback URLs are not registered in the defaults map, so no
    # collision occurs.  Verify the runtimes were attached to each app.
    assert hasattr(app1.state, "openclaw_runtime")
    assert hasattr(app2.state, "openclaw_runtime")
    assert openclaw_mod.openclaw_model._CURRENT_APP_OPENCLAW_DEFAULTS == {}
    assert openclaw_mod.openclaw_model._CURRENT_APP_OPENCLAW_DEFAULT_COUNTS == {}


def test_attach_openclaw_to_fastapi_releases_current_app_defaults_when_app_is_discarded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENCLAW_PROXY_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROXY_HOST", raising=False)
    monkeypatch.setenv("OPENCLAW_PROXY_PORT", "8000")
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULT_COUNTS", {}, raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULT_PATTERNS", [], raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULT_PATTERN_COUNTS", {}, raising=False)

    first_config = replace(
        _build_openclaw_config(tmp_path / "first"),
        default_model="openclaw:first",
        provider_model="openai/gpt-4o",
    )
    attach_openclaw_to_fastapi(FastAPI(), first_config)
    gc.collect()

    second_config = replace(
        _build_openclaw_config(tmp_path / "second"),
        default_model="openclaw:second",
        provider_model="openai/gpt-5.4-mini",
    )
    attach_openclaw_to_fastapi(FastAPI(), second_config)


def test_attach_openclaw_to_fastapi_keeps_distinct_current_app_defaults_separate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENCLAW_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROVIDER_MODEL", raising=False)
    monkeypatch.setenv("OPENCLAW_PROXY_BASE_URL", "http://127.0.0.1:8000/openclaw/v1")
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)

    first_app = FastAPI()
    first_config = replace(
        _build_openclaw_config(tmp_path / "first"),
        default_model="openclaw:first",
        provider_model="openai/gpt-4o",
    )
    attach_openclaw_to_fastapi(first_app, first_config)

    monkeypatch.setenv("OPENCLAW_PROXY_BASE_URL", "http://127.0.0.1:9000/openclaw/v1")
    second_app = FastAPI()
    second_config = replace(
        _build_openclaw_config(tmp_path / "second"),
        port=9000,
        default_model="openclaw:second",
        provider_model="openai/gpt-5.4-mini",
    )
    attach_openclaw_to_fastapi(second_app, second_config)

    first_model = build_openclaw_responses_model(base_url="http://127.0.0.1:8000/openclaw/v1", api_key="first-token")
    second_model = build_openclaw_responses_model(base_url="http://127.0.0.1:9000/openclaw/v1", api_key="second-token")

    assert first_model.model == "openclaw:first"
    assert second_model.model == "openclaw:second"


def test_attach_openclaw_to_fastapi_uses_current_app_defaults_for_public_proxy_urls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENCLAW_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("OPENCLAW_PROVIDER_MODEL", raising=False)
    monkeypatch.setenv("OPENCLAW_PROXY_BASE_URL", "https://worker.example/openclaw/v1")
    monkeypatch.setenv("APP_TOKEN", "app-token")
    monkeypatch.setenv("OPENCLAW_PROXY_API_KEY", "proxy-token")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "gateway-token")
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)

    app = FastAPI()
    config = replace(
        _build_openclaw_config(tmp_path),
        port=9000,
        default_model="openclaw:custom",
        provider_model="openai/gpt-5.4-mini",
    )
    attach_openclaw_to_fastapi(app, config)

    model = build_openclaw_responses_model(base_url="https://worker.example/openclaw/v1")

    assert model.model == "openclaw:custom"
    assert get_usage_tracking_model_name(model) == "openai/gpt-5.4-mini"
    assert model._client.api_key == "app-token"


def test_attach_openclaw_to_fastapi_does_not_treat_other_public_proxy_urls_as_current_app(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENCLAW_DEFAULT_MODEL", raising=False)
    monkeypatch.setenv("OPENCLAW_PROVIDER_MODEL", "openai/gpt-5.4-mini")
    monkeypatch.setenv("OPENCLAW_PROXY_BASE_URL", "https://external.example/openclaw/v1")
    monkeypatch.setenv("APP_TOKEN", "app-token")
    monkeypatch.setenv("OPENCLAW_PROXY_API_KEY", "proxy-token")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "gateway-token")
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)

    app = FastAPI()
    config = replace(
        _build_openclaw_config(tmp_path),
        port=9000,
        default_model="openclaw:custom",
        provider_model="openai/gpt-4o",
    )
    attach_openclaw_to_fastapi(app, config)

    model = build_openclaw_responses_model(base_url="https://other.example/openclaw/v1")

    assert model.model == "openclaw:main"
    assert get_usage_tracking_model_name(model) == "openclaw:main"
    assert model._client.api_key == "proxy-token"

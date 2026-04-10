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


@pytest.fixture(autouse=True)
def _reset_openclaw_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULT_COUNTS", {}, raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULT_PATTERNS", [], raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULT_PATTERN_COUNTS", {}, raising=False)


def _clear_openclaw_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [
        "APP_TOKEN",
        "OPENCLAW_DEFAULT_MODEL",
        "OPENCLAW_GATEWAY_TOKEN",
        "OPENCLAW_PROVIDER_MODEL",
        "OPENCLAW_PROXY_API_KEY",
        "OPENCLAW_PROXY_BASE_URL",
        "OPENCLAW_PROXY_HOST",
        "OPENCLAW_PROXY_PORT",
        "PORT",
    ]:
        monkeypatch.delenv(name, raising=False)


def test_build_openclaw_model_uses_current_app_proxy_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _clear_openclaw_env(monkeypatch)
    monkeypatch.setenv("OPENCLAW_PROXY_PORT", "9000")
    monkeypatch.setenv("APP_TOKEN", "app-token")
    monkeypatch.setenv("OPENCLAW_PROXY_API_KEY", "proxy-token")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "gateway-token")

    config = replace(
        _build_openclaw_config(tmp_path),
        port=9000,
        default_model="openclaw:custom",
        provider_model="anthropic/claude-sonnet-4-5",
    )
    attach_openclaw_to_fastapi(FastAPI(), config)

    model = build_openclaw_responses_model(base_url="http://127.0.0.1:9000/openclaw/v1")

    assert model.model == "openclaw:custom"
    assert get_usage_tracking_model_name(model) == "anthropic/claude-sonnet-4-5"
    assert model._client.api_key == "app-token"


@pytest.mark.parametrize(
    ("server_url", "base_url"),
    [
        ("http://localhost:9000", "http://127.0.0.1:9000/openclaw/v1"),
        ("https://example.com/{stage}", "https://example.com/prod/openclaw/v1"),
    ],
)
def test_attach_openclaw_uses_app_server_urls_for_current_app_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    server_url: str,
    base_url: str,
) -> None:
    _clear_openclaw_env(monkeypatch)
    monkeypatch.setenv("APP_TOKEN", "app-token")
    monkeypatch.setenv("OPENCLAW_PROXY_API_KEY", "proxy-token")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "gateway-token")

    app = FastAPI(servers=[{"url": server_url}])
    attach_openclaw_to_fastapi(
        app,
        replace(
            _build_openclaw_config(tmp_path),
            default_model="openclaw:custom",
            provider_model="anthropic/claude-sonnet-4-5",
        ),
    )

    model = build_openclaw_responses_model(base_url=base_url)

    assert model.model == "openclaw:custom"
    assert get_usage_tracking_model_name(model) == "anthropic/claude-sonnet-4-5"
    assert model._client.api_key == "app-token"


def test_attach_openclaw_ignores_relative_server_urls_for_current_app_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_openclaw_env(monkeypatch)
    monkeypatch.setenv("APP_TOKEN", "app-token")
    monkeypatch.setenv("OPENCLAW_PROXY_API_KEY", "proxy-token")

    app = FastAPI(servers=[{"url": "/api"}])
    attach_openclaw_to_fastapi(app, _build_openclaw_config(tmp_path))

    model = build_openclaw_responses_model(base_url="https://example.com/api/openclaw/v1")

    assert model.model == "openclaw:main"
    assert get_usage_tracking_model_name(model) == "openclaw:main"
    assert model._client.api_key == "proxy-token"


def test_attach_openclaw_rejects_conflicting_current_app_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_openclaw_env(monkeypatch)
    monkeypatch.setenv("OPENCLAW_PROXY_PORT", "8000")

    attach_openclaw_to_fastapi(
        FastAPI(),
        replace(
            _build_openclaw_config(tmp_path / "first"),
            default_model="openclaw:first",
            provider_model="openai/gpt-4o",
        ),
    )

    with pytest.raises(ValueError, match="Conflicting current-app OpenClaw defaults"):
        attach_openclaw_to_fastapi(
            FastAPI(),
            replace(
                _build_openclaw_config(tmp_path / "second"),
                default_model="openclaw:second",
                provider_model="openai/gpt-5.4-mini",
            ),
        )


def test_attach_openclaw_rolls_back_partial_registration_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_openclaw_env(monkeypatch)
    monkeypatch.setenv("OPENCLAW_PROXY_PORT", "9000")

    conflict_url = "https://conflict.example/openclaw/v1"
    openclaw_mod.openclaw_model.register_current_app_openclaw_defaults(
        default_model="openclaw:existing",
        provider_model="openai/gpt-4o",
        base_url=conflict_url,
    )

    with pytest.raises(ValueError, match="Conflicting"):
        attach_openclaw_to_fastapi(
            FastAPI(servers=[{"url": "https://conflict.example"}]),
            replace(
                _build_openclaw_config(tmp_path),
                default_model="openclaw:new",
                provider_model="openai/gpt-5.4-mini",
            ),
        )

    default_url_key = openclaw_mod.openclaw_model._normalize_openclaw_proxy_url("http://127.0.0.1:9000/openclaw/v1")
    assert default_url_key not in openclaw_mod.openclaw_model._CURRENT_APP_OPENCLAW_DEFAULTS
    assert default_url_key not in openclaw_mod.openclaw_model._CURRENT_APP_OPENCLAW_DEFAULT_COUNTS


def test_attach_openclaw_releases_defaults_when_app_is_garbage_collected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_openclaw_env(monkeypatch)
    monkeypatch.setenv("OPENCLAW_PROXY_PORT", "8000")

    attach_openclaw_to_fastapi(
        FastAPI(),
        replace(
            _build_openclaw_config(tmp_path / "first"),
            default_model="openclaw:first",
            provider_model="openai/gpt-4o",
        ),
    )
    gc.collect()

    attach_openclaw_to_fastapi(
        FastAPI(),
        replace(
            _build_openclaw_config(tmp_path / "second"),
            default_model="openclaw:second",
            provider_model="openai/gpt-5.4-mini",
        ),
    )


def test_attach_openclaw_keeps_distinct_proxy_defaults_separate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_openclaw_env(monkeypatch)
    monkeypatch.setenv("OPENCLAW_PROXY_BASE_URL", "http://127.0.0.1:8000/openclaw/v1")
    first_app = FastAPI()
    second_app = FastAPI()

    attach_openclaw_to_fastapi(
        first_app,
        replace(
            _build_openclaw_config(tmp_path / "first"),
            default_model="openclaw:first",
            provider_model="openai/gpt-4o",
        ),
    )

    monkeypatch.setenv("OPENCLAW_PROXY_BASE_URL", "http://127.0.0.1:9000/openclaw/v1")
    attach_openclaw_to_fastapi(
        second_app,
        replace(
            _build_openclaw_config(tmp_path / "second"),
            port=9000,
            default_model="openclaw:second",
            provider_model="openai/gpt-5.4-mini",
        ),
    )

    first_model = build_openclaw_responses_model(base_url="http://127.0.0.1:8000/openclaw/v1", api_key="first-token")
    second_model = build_openclaw_responses_model(
        base_url="http://127.0.0.1:9000/openclaw/v1",
        api_key="second-token",
    )

    assert first_model.model == "openclaw:first"
    assert second_model.model == "openclaw:second"


def test_attach_openclaw_uses_public_proxy_defaults_for_exact_current_app_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_openclaw_env(monkeypatch)
    monkeypatch.setenv("OPENCLAW_PROXY_BASE_URL", "https://worker.example/openclaw/v1")
    monkeypatch.setenv("APP_TOKEN", "app-token")
    monkeypatch.setenv("OPENCLAW_PROXY_API_KEY", "proxy-token")

    attach_openclaw_to_fastapi(
        FastAPI(),
        replace(
            _build_openclaw_config(tmp_path),
            default_model="openclaw:custom",
            provider_model="openai/gpt-5.4-mini",
        ),
    )

    model = build_openclaw_responses_model(base_url="https://worker.example/openclaw/v1")

    assert model.model == "openclaw:custom"
    assert get_usage_tracking_model_name(model) == "openai/gpt-5.4-mini"
    assert model._client.api_key == "app-token"


def test_attach_openclaw_does_not_reuse_public_proxy_defaults_for_other_urls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_openclaw_env(monkeypatch)
    monkeypatch.setenv("OPENCLAW_PROXY_BASE_URL", "https://external.example/openclaw/v1")
    monkeypatch.setenv("OPENCLAW_PROVIDER_MODEL", "openai/gpt-5.4-mini")
    monkeypatch.setenv("APP_TOKEN", "app-token")
    monkeypatch.setenv("OPENCLAW_PROXY_API_KEY", "proxy-token")

    attach_openclaw_to_fastapi(
        FastAPI(),
        replace(
            _build_openclaw_config(tmp_path),
            default_model="openclaw:custom",
            provider_model="openai/gpt-4o",
        ),
    )

    model = build_openclaw_responses_model(base_url="https://other.example/openclaw/v1")

    assert model.model == "openclaw:main"
    assert get_usage_tracking_model_name(model) == "openclaw:main"
    assert model._client.api_key == "proxy-token"

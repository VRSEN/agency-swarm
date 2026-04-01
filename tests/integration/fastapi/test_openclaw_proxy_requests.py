from __future__ import annotations

import gzip
from pathlib import Path

import httpx
import pytest

from agency_swarm.integrations import openclaw as openclaw_mod
from agency_swarm.integrations.openclaw import (
    OpenClawIntegrationConfig,
    OpenClawRuntime,
    normalize_openclaw_responses_request,
)


def test_openclaw_config_manual_construction_defaults_to_full_tool_mode(tmp_path: Path) -> None:
    home_dir = tmp_path / "openclaw"
    config = OpenClawIntegrationConfig(
        autostart=False,
        host="127.0.0.1",
        port=18789,
        gateway_token="gateway-token",
        home_dir=home_dir,
        state_dir=home_dir / "state",
        config_path=home_dir / "openclaw.json",
        log_path=home_dir / "logs" / "openclaw-gateway.log",
        startup_timeout_seconds=5.0,
        proxy_timeout_seconds=30.0,
        default_model="openclaw:main",
        provider_model="openai/gpt-5.4-mini",
        gateway_command="openclaw gateway",
    )

    assert config.tool_mode == "full"


def test_openclaw_health_returns_runtime_snapshot(tmp_path: Path) -> None:
    runtime = OpenClawRuntime(
        OpenClawIntegrationConfig(
            autostart=False,
            host="127.0.0.1",
            port=18789,
            gateway_token="gateway-token",
            home_dir=tmp_path / "openclaw",
            state_dir=tmp_path / "openclaw" / "state",
            config_path=tmp_path / "openclaw" / "openclaw.json",
            log_path=tmp_path / "openclaw" / "logs" / "openclaw-gateway.log",
            startup_timeout_seconds=5.0,
            proxy_timeout_seconds=30.0,
            default_model="openclaw:main",
            provider_model="openai/gpt-5.4-mini",
            gateway_command="openclaw gateway",
        )
    )

    payload = runtime.health()

    assert payload["running"] is False
    assert payload["upstream_base_url"] == "http://127.0.0.1:18789"
    assert payload["home_dir"].endswith("openclaw")
    assert payload["state_dir"].endswith("openclaw/state")


def test_openclaw_normalization_validation_error_paths() -> None:
    with pytest.raises(ValueError, match="model is required"):
        normalize_openclaw_responses_request({"input": "hello"})
    with pytest.raises(ValueError, match="input is required"):
        normalize_openclaw_responses_request({"model": "openclaw:main"})
    with pytest.raises(ValueError, match="input must be a string or list"):
        normalize_openclaw_responses_request({"model": "openclaw:main", "input": {"bad": "shape"}})
    with pytest.raises(ValueError, match="input list items must be JSON objects"):
        normalize_openclaw_responses_request({"model": "openclaw:main", "input": ["bad"]})
    with pytest.raises(ValueError, match="input message role must be a non-empty string"):
        normalize_openclaw_responses_request(
            {"model": "openclaw:main", "input": [{"type": "message", "content": "missing role"}]}
        )
    with pytest.raises(ValueError, match="input message content must be a string or list"):
        normalize_openclaw_responses_request(
            {"model": "openclaw:main", "input": [{"role": "user", "content": {"bad": "shape"}}]}
        )

    normalized = normalize_openclaw_responses_request(
        {
            "model": "openclaw:main",
            "input": "hello",
            "tool_choice": "unsupported",
            "metadata": "bad-metadata",
        }
    )
    assert "tool_choice" not in normalized
    assert "metadata" not in normalized


def test_openclaw_header_helpers() -> None:
    assert openclaw_mod._make_upstream_headers("") == {"Content-Type": "application/json"}
    assert openclaw_mod._make_upstream_headers("token") == {
        "Content-Type": "application/json",
        "Authorization": "Bearer token",
    }

    upstream = httpx.Response(
        status_code=200,
        content=gzip.compress(b"ok"),
        headers={
            "content-type": "application/json",
            "x-request-id": "req-1",
            "content-encoding": "gzip",
            "content-length": "2",
        },
    )
    assert "content-encoding" in openclaw_mod._passthrough_response_headers(upstream, decoded_body=False)
    assert "content-encoding" not in openclaw_mod._passthrough_response_headers(upstream, decoded_body=True)

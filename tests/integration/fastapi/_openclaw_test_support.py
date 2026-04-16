from __future__ import annotations

import gc
from pathlib import Path

import pytest

from agency_swarm.integrations import openclaw as openclaw_mod
from agency_swarm.integrations.openclaw import OpenClawIntegrationConfig


def _build_openclaw_config(tmp_path: Path) -> OpenClawIntegrationConfig:
    home_dir = tmp_path / "openclaw"
    return OpenClawIntegrationConfig(
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
        tool_mode="full",
    )


def reset_openclaw_current_app_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    gc.collect()
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULTS", {}, raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULT_COUNTS", {}, raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULT_PATTERNS", [], raising=False)
    monkeypatch.setattr(openclaw_mod.openclaw_model, "_CURRENT_APP_OPENCLAW_DEFAULT_PATTERN_COUNTS", {}, raising=False)


build_openclaw_config = _build_openclaw_config

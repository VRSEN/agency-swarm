from __future__ import annotations

from pathlib import Path

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


build_openclaw_config = _build_openclaw_config

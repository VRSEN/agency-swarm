from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from openclaw_runtime import OpenClawRuntime, OpenClawRuntimeConfig


def _build_runtime_config(tmp_path: Path) -> OpenClawRuntimeConfig:
    data_dir = tmp_path / "openclaw"
    return OpenClawRuntimeConfig(
        autostart=True,
        host="127.0.0.1",
        port=18789,
        gateway_token="test-token",
        data_dir=data_dir,
        state_dir=data_dir / "state",
        config_path=data_dir / "openclaw.json",
        log_path=data_dir / "openclaw-gateway.log",
        startup_timeout_seconds=30,
        default_model="openai/gpt-4o-mini",
        gateway_command=None,
    )


def _read_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_ensure_layout_writes_latest_gateway_and_agent_defaults_config(tmp_path: Path) -> None:
    runtime = OpenClawRuntime(_build_runtime_config(tmp_path))
    runtime.ensure_layout()

    written = _read_config(runtime.config.config_path)
    assert "agent" not in written
    assert written["gateway"]["mode"] == "local"
    assert written["gateway"]["bind"] == "loopback"
    assert written["gateway"]["port"] == 18789
    assert written["gateway"]["auth"]["mode"] == "token"
    assert written["gateway"]["auth"]["token"] == "test-token"
    assert written["gateway"]["http"]["endpoints"]["responses"]["enabled"] is True
    assert written["agents"]["defaults"]["model"]["primary"] == "openai/gpt-4o-mini"


def test_ensure_layout_migrates_legacy_agent_model_to_agents_defaults(tmp_path: Path) -> None:
    runtime = OpenClawRuntime(_build_runtime_config(tmp_path))
    runtime.config.config_path.parent.mkdir(parents=True, exist_ok=True)
    runtime.config.config_path.write_text(
        json.dumps({"agent": {"model": "anthropic/claude-sonnet-4-5"}}),
        encoding="utf-8",
    )

    runtime.ensure_layout()

    written = _read_config(runtime.config.config_path)
    assert "agent" not in written
    assert written["agents"]["defaults"]["model"]["primary"] == "anthropic/claude-sonnet-4-5"


def test_ensure_layout_preserves_existing_agents_defaults_model(tmp_path: Path) -> None:
    runtime = OpenClawRuntime(_build_runtime_config(tmp_path))
    runtime.config.config_path.parent.mkdir(parents=True, exist_ok=True)
    runtime.config.config_path.write_text(
        json.dumps(
            {
                "agents": {
                    "defaults": {
                        "model": {
                            "primary": "openai/gpt-5.2",
                            "fallbacks": ["openai/gpt-4o-mini"],
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    runtime.ensure_layout()

    written = _read_config(runtime.config.config_path)
    assert written["agents"]["defaults"]["model"] == {
        "primary": "openai/gpt-5.2",
        "fallbacks": ["openai/gpt-4o-mini"],
    }


def test_resolve_openai_api_key_prefers_repo_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text('OPENAI_API_KEY="sk-from-repo-env"\n', encoding="utf-8")
    monkeypatch.setattr(OpenClawRuntime, "_candidate_env_paths", staticmethod(lambda: [env_file]))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-process-env")

    key, source_path = OpenClawRuntime._resolve_openai_api_key()

    assert key == "sk-from-repo-env"
    assert source_path == env_file


def test_resolve_openai_api_key_falls_back_to_process_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(OpenClawRuntime, "_candidate_env_paths", staticmethod(lambda: []))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-process-env")

    key, source_path = OpenClawRuntime._resolve_openai_api_key()

    assert key == "sk-from-process-env"
    assert source_path is None


def test_resolve_openai_api_key_returns_none_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(OpenClawRuntime, "_candidate_env_paths", staticmethod(lambda: []))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    key, source_path = OpenClawRuntime._resolve_openai_api_key()

    assert key is None
    assert source_path is None

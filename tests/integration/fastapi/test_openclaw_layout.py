from __future__ import annotations

import json
import os
import stat
from dataclasses import replace
from pathlib import Path

import pytest

from agency_swarm.integrations import openclaw as openclaw_mod
from agency_swarm.integrations.openclaw import OpenClawRuntime
from tests.integration.fastapi._openclaw_test_support import _build_openclaw_config


def test_openclaw_ensure_layout_creates_config_parent_dir(tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    custom_config_path = tmp_path / "external" / "nested" / "openclaw.json"
    runtime = OpenClawRuntime(replace(config, config_path=custom_config_path))

    runtime.ensure_layout()

    assert custom_config_path.exists()
    assert custom_config_path.parent.is_dir()
    if os.name != "nt":
        assert stat.S_IMODE(custom_config_path.stat().st_mode) == 0o600


def test_openclaw_ensure_layout_writes_config_with_secure_create_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _build_openclaw_config(tmp_path)
    runtime = OpenClawRuntime(config)
    original_open = openclaw_mod.os.open
    seen_modes: list[int] = []

    def _open(path: os.PathLike[str] | str, flags: int, mode: int = 0o777) -> int:
        seen_modes.append(mode)
        return original_open(path, flags, mode)

    monkeypatch.setattr(openclaw_mod.os, "open", _open)

    runtime.ensure_layout()

    assert seen_modes
    assert seen_modes[-1] == 0o600


def test_openclaw_ensure_layout_defaults_workspace_to_home_workspace(tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    runtime = OpenClawRuntime(config)

    runtime.ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))

    assert payload["agents"]["defaults"]["workspace"] == str(config.workspace_dir)
    assert config.workspace_dir.is_dir()


def test_openclaw_ensure_layout_keeps_existing_workspace_override(tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    custom_workspace = tmp_path / "custom-workspace"
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps({"agents": {"defaults": {"workspace": str(custom_workspace)}}}),
        encoding="utf-8",
    )

    OpenClawRuntime(config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))

    assert payload["agents"]["defaults"]["workspace"] == str(custom_workspace)
    assert not config.workspace_dir.exists()


def test_openclaw_ensure_layout_replaces_blank_workspace_override(tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps({"agents": {"defaults": {"workspace": "   "}}}),
        encoding="utf-8",
    )

    OpenClawRuntime(config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))

    assert payload["agents"]["defaults"]["workspace"] == str(config.workspace_dir)
    assert config.workspace_dir.is_dir()


def test_openclaw_ensure_layout_migrates_legacy_workspace_when_default_is_missing(tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    legacy_workspace = config.legacy_workspace_dir
    legacy_workspace.mkdir(parents=True, exist_ok=True)
    (legacy_workspace / "AGENTS.md").write_text("legacy", encoding="utf-8")

    OpenClawRuntime(config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))

    assert payload["agents"]["defaults"]["workspace"] == str(config.workspace_dir)
    assert (config.workspace_dir / "AGENTS.md").read_text(encoding="utf-8") == "legacy"
    assert not legacy_workspace.exists()


def test_openclaw_ensure_layout_preserves_legacy_workspace_when_new_and_old_both_exist(tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    legacy_workspace = config.legacy_workspace_dir
    legacy_workspace.mkdir(parents=True, exist_ok=True)
    (legacy_workspace / "AGENTS.md").write_text("legacy", encoding="utf-8")
    config.workspace_dir.mkdir(parents=True, exist_ok=True)
    (config.workspace_dir / "AGENTS.md").write_text("new", encoding="utf-8")

    OpenClawRuntime(config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))

    assert payload["agents"]["defaults"]["workspace"] == str(legacy_workspace)
    assert (legacy_workspace / "AGENTS.md").read_text(encoding="utf-8") == "legacy"
    assert (config.workspace_dir / "AGENTS.md").read_text(encoding="utf-8") == "new"


def test_openclaw_ensure_layout_merges_legacy_workspace_into_empty_new_dir(tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    legacy_workspace = config.legacy_workspace_dir
    legacy_workspace.mkdir(parents=True, exist_ok=True)
    (legacy_workspace / "AGENTS.md").write_text("legacy", encoding="utf-8")
    config.workspace_dir.mkdir(parents=True, exist_ok=True)

    OpenClawRuntime(config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))

    assert payload["agents"]["defaults"]["workspace"] == str(config.workspace_dir)
    assert (config.workspace_dir / "AGENTS.md").read_text(encoding="utf-8") == "legacy"
    assert not legacy_workspace.exists()


def test_openclaw_ensure_layout_keeps_explicit_agent_workspace_override(tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    legacy_workspace = config.legacy_workspace_dir
    legacy_workspace.mkdir(parents=True, exist_ok=True)
    (legacy_workspace / "AGENTS.md").write_text("legacy", encoding="utf-8")
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps({"agents": {"list": [{"id": "main", "workspace": str(legacy_workspace)}]}}),
        encoding="utf-8",
    )

    OpenClawRuntime(config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))

    assert payload["agents"]["list"][0]["workspace"] == str(legacy_workspace)
    assert (legacy_workspace / "AGENTS.md").read_text(encoding="utf-8") == "legacy"
    assert not config.workspace_dir.exists()


def test_openclaw_ensure_layout_keeps_default_workspace_migration_when_other_agent_has_override(tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    specialist_workspace = tmp_path / "specialist-workspace"
    config.config_path.write_text(
        json.dumps(
            {
                "agents": {
                    "list": [
                        {"id": "main", "default": True},
                        {"id": "specialist", "workspace": str(specialist_workspace)},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    OpenClawRuntime(config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))

    assert payload["agents"]["defaults"]["workspace"] == str(config.workspace_dir)
    assert payload["agents"]["list"][1]["workspace"] == str(specialist_workspace)


def test_openclaw_ensure_layout_uses_profile_aware_workspace_suffix(tmp_path: Path) -> None:
    config = replace(_build_openclaw_config(tmp_path), profile="team-a")

    OpenClawRuntime(config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))

    assert payload["agents"]["defaults"]["workspace"] == str(config.home_dir / "workspace-team-a")
    assert (config.home_dir / "workspace-team-a").is_dir()


def test_openclaw_ensure_layout_uses_env_profile_for_manual_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENCLAW_PROFILE", "team-a")
    config = _build_openclaw_config(tmp_path)

    OpenClawRuntime(config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))

    assert payload["agents"]["defaults"]["workspace"] == str(config.home_dir / "workspace-team-a")


def test_openclaw_ensure_layout_treats_default_profile_as_unsuffixed_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENCLAW_PROFILE", "default")
    config = _build_openclaw_config(tmp_path)

    OpenClawRuntime(config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))

    assert payload["agents"]["defaults"]["workspace"] == str(config.home_dir / "workspace")


def test_openclaw_ensure_layout_fails_cleanly_when_workspace_path_is_a_file(tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    config.workspace_dir.parent.mkdir(parents=True, exist_ok=True)
    config.workspace_dir.write_text("not-a-dir", encoding="utf-8")

    with pytest.raises(RuntimeError, match="workspace path collision"):
        OpenClawRuntime(config).ensure_layout()


def test_openclaw_ensure_layout_normalizes_existing_non_dict_config_sections(tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps(
            {
                "gateway": [],
                "agents": {"defaults": []},
            }
        ),
        encoding="utf-8",
    )
    runtime = OpenClawRuntime(config)

    runtime.ensure_layout()

    saved = json.loads(config.config_path.read_text(encoding="utf-8"))
    assert saved["gateway"]["auth"]["mode"] == "token"
    assert saved["gateway"]["http"]["endpoints"]["responses"]["enabled"] is True
    assert saved["agents"]["defaults"]["model"] == {"primary": "openai/gpt-5.4-mini"}
    assert saved["agents"]["defaults"]["workspace"] == str(config.workspace_dir)

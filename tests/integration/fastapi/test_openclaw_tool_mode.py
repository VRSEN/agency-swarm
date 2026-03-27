from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from agency_swarm.integrations import openclaw as openclaw_mod
from agency_swarm.integrations.openclaw import OpenClawRuntime
from tests.integration.fastapi._openclaw_test_support import _build_openclaw_config


def test_openclaw_worker_tool_mode_disables_competing_native_messaging(tmp_path: Path) -> None:
    config = replace(_build_openclaw_config(tmp_path), tool_mode="worker")
    runtime = OpenClawRuntime(config)

    runtime.ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))
    assert payload["tools"]["agentToAgent"]["enabled"] is False
    assert payload["tools"]["deny"] == ["message", "sessions_send", "sessions_spawn"]


def test_openclaw_full_tool_mode_restores_previous_settings(tmp_path: Path) -> None:
    config = replace(_build_openclaw_config(tmp_path), tool_mode="worker")
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps(
            {
                "tools": {
                    "agentToAgent": {"enabled": True, "mode": "custom"},
                    "deny": ["browser"],
                }
            }
        ),
        encoding="utf-8",
    )

    OpenClawRuntime(config).ensure_layout()

    restore_config = replace(config, tool_mode="full")
    OpenClawRuntime(restore_config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))
    assert payload["tools"]["agentToAgent"] == {"enabled": True, "mode": "custom"}
    assert payload["tools"]["deny"] == ["browser"]
    backup_path = openclaw_mod._tool_mode_backup_path(config.config_path)
    assert not backup_path.exists()


def test_openclaw_full_tool_mode_keeps_backup_when_config_write_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = replace(_build_openclaw_config(tmp_path), tool_mode="worker")
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps(
            {
                "tools": {
                    "agentToAgent": {"enabled": True, "mode": "custom"},
                    "deny": ["browser"],
                }
            }
        ),
        encoding="utf-8",
    )

    OpenClawRuntime(config).ensure_layout()
    backup_path = openclaw_mod._tool_mode_backup_path(config.config_path)
    assert backup_path.exists()

    original_open = openclaw_mod.os.open

    def _failing_open(path: str | os.PathLike[str], flags: int, mode: int = 0o777) -> int:
        if Path(path) == config.config_path:
            raise OSError("disk full")
        return original_open(path, flags, mode)

    monkeypatch.setattr(openclaw_mod.os, "open", _failing_open)

    with pytest.raises(OSError, match="disk full"):
        OpenClawRuntime(replace(config, tool_mode="full")).ensure_layout()

    assert backup_path.exists()


def test_openclaw_full_tool_mode_keeps_backup_when_tool_mode_backup_is_unreadable(tmp_path: Path) -> None:
    config = replace(_build_openclaw_config(tmp_path), tool_mode="worker")
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps(
            {
                "tools": {
                    "agentToAgent": {"enabled": True, "mode": "custom"},
                    "deny": ["browser"],
                }
            }
        ),
        encoding="utf-8",
    )

    OpenClawRuntime(config).ensure_layout()
    backup_path = openclaw_mod._tool_mode_backup_path(config.config_path)
    backup_path.write_text("{invalid", encoding="utf-8")

    OpenClawRuntime(replace(config, tool_mode="full")).ensure_layout()

    assert backup_path.exists()


def test_openclaw_full_tool_mode_preserves_deleted_agent_to_agent_block(tmp_path: Path) -> None:
    config = replace(_build_openclaw_config(tmp_path), tool_mode="worker")
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps(
            {
                "tools": {
                    "agentToAgent": {"enabled": True, "mode": "custom"},
                    "deny": ["browser"],
                }
            }
        ),
        encoding="utf-8",
    )

    OpenClawRuntime(config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))
    payload["tools"].pop("agentToAgent")
    config.config_path.write_text(json.dumps(payload), encoding="utf-8")

    OpenClawRuntime(replace(config, tool_mode="full")).ensure_layout()

    restored = json.loads(config.config_path.read_text(encoding="utf-8"))
    assert "agentToAgent" not in restored["tools"]
    assert restored["tools"]["deny"] == ["browser"]


def test_openclaw_full_tool_mode_preserves_user_changes_made_while_worker_mode_is_active(tmp_path: Path) -> None:
    config = replace(_build_openclaw_config(tmp_path), tool_mode="worker")
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps(
            {
                "tools": {
                    "agentToAgent": {"enabled": True, "mode": "custom"},
                    "deny": ["browser"],
                }
            }
        ),
        encoding="utf-8",
    )

    OpenClawRuntime(config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))
    payload["tools"]["deny"].append("shell")
    payload["tools"]["agentToAgent"]["notes"] = "keep-me"
    config.config_path.write_text(json.dumps(payload), encoding="utf-8")

    OpenClawRuntime(replace(config, tool_mode="full")).ensure_layout()

    restored = json.loads(config.config_path.read_text(encoding="utf-8"))
    assert restored["tools"]["agentToAgent"] == {
        "enabled": True,
        "mode": "custom",
        "notes": "keep-me",
    }
    assert restored["tools"]["deny"] == ["browser", "shell"]


def test_openclaw_full_tool_mode_preserves_user_edits_to_existing_agent_to_agent_keys(tmp_path: Path) -> None:
    config = replace(_build_openclaw_config(tmp_path), tool_mode="worker")
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps(
            {
                "tools": {
                    "agentToAgent": {"enabled": True, "mode": "custom"},
                    "deny": ["browser"],
                }
            }
        ),
        encoding="utf-8",
    )

    OpenClawRuntime(config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))
    payload["tools"]["agentToAgent"]["mode"] = "strict"
    config.config_path.write_text(json.dumps(payload), encoding="utf-8")

    OpenClawRuntime(replace(config, tool_mode="full")).ensure_layout()

    restored = json.loads(config.config_path.read_text(encoding="utf-8"))
    assert restored["tools"]["agentToAgent"] == {"enabled": True, "mode": "strict"}


def test_openclaw_full_tool_mode_preserves_deleted_agent_to_agent_keys(tmp_path: Path) -> None:
    config = replace(_build_openclaw_config(tmp_path), tool_mode="worker")
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps(
            {
                "tools": {
                    "agentToAgent": {"enabled": True, "mode": "custom", "scope": "full"},
                    "deny": ["browser"],
                }
            }
        ),
        encoding="utf-8",
    )

    OpenClawRuntime(config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))
    payload["tools"]["agentToAgent"].pop("mode")
    config.config_path.write_text(json.dumps(payload), encoding="utf-8")

    OpenClawRuntime(replace(config, tool_mode="full")).ensure_layout()

    restored = json.loads(config.config_path.read_text(encoding="utf-8"))
    assert restored["tools"]["agentToAgent"] == {"enabled": True, "scope": "full"}


def test_openclaw_full_tool_mode_preserves_deleted_deny_entries(tmp_path: Path) -> None:
    config = replace(_build_openclaw_config(tmp_path), tool_mode="worker")
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps(
            {
                "tools": {
                    "agentToAgent": {"enabled": True, "mode": "custom"},
                    "deny": ["browser", "shell"],
                }
            }
        ),
        encoding="utf-8",
    )

    OpenClawRuntime(config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))
    payload["tools"]["deny"] = ["shell"]
    config.config_path.write_text(json.dumps(payload), encoding="utf-8")
    stat_result = config.config_path.stat()
    os.utime(config.config_path, ns=(stat_result.st_atime_ns, stat_result.st_mtime_ns + 1))

    OpenClawRuntime(replace(config, tool_mode="full")).ensure_layout()

    restored = json.loads(config.config_path.read_text(encoding="utf-8"))
    assert restored["tools"]["deny"] == ["shell"]


def test_openclaw_full_tool_mode_preserves_explicit_worker_style_deny_entries(tmp_path: Path) -> None:
    config = replace(_build_openclaw_config(tmp_path), tool_mode="worker")
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps(
            {
                "tools": {
                    "agentToAgent": {"enabled": True, "mode": "custom"},
                    "deny": ["browser"],
                }
            }
        ),
        encoding="utf-8",
    )

    OpenClawRuntime(config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))
    payload["tools"]["deny"] = ["browser", "message"]
    config.config_path.write_text(json.dumps(payload), encoding="utf-8")

    OpenClawRuntime(replace(config, tool_mode="full")).ensure_layout()

    restored = json.loads(config.config_path.read_text(encoding="utf-8"))
    assert restored["tools"]["deny"] == ["browser", "message"]


def test_openclaw_full_tool_mode_restores_agent_to_agent_when_only_deny_changes(tmp_path: Path) -> None:
    config = replace(_build_openclaw_config(tmp_path), tool_mode="worker")
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps(
            {
                "tools": {
                    "agentToAgent": {"enabled": True, "mode": "custom"},
                    "deny": ["browser"],
                }
            }
        ),
        encoding="utf-8",
    )

    OpenClawRuntime(config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))
    payload["tools"]["deny"].append("shell")
    config.config_path.write_text(json.dumps(payload), encoding="utf-8")

    OpenClawRuntime(replace(config, tool_mode="full")).ensure_layout()

    restored = json.loads(config.config_path.read_text(encoding="utf-8"))
    assert restored["tools"]["agentToAgent"] == {"enabled": True, "mode": "custom"}
    assert restored["tools"]["deny"] == ["browser", "shell"]


def test_openclaw_full_tool_mode_restores_original_agent_to_agent_after_format_only_rewrite(tmp_path: Path) -> None:
    config = replace(_build_openclaw_config(tmp_path), tool_mode="worker")
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps(
            {
                "tools": {
                    "agentToAgent": {"enabled": True, "mode": "custom"},
                    "deny": ["browser"],
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    OpenClawRuntime(config).ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))
    config.config_path.write_text(json.dumps(payload), encoding="utf-8")

    OpenClawRuntime(replace(config, tool_mode="full")).ensure_layout()

    restored = json.loads(config.config_path.read_text(encoding="utf-8"))
    assert restored["tools"]["agentToAgent"] == {"enabled": True, "mode": "custom"}
    assert restored["tools"]["deny"] == ["browser"]


def test_openclaw_full_tool_mode_preserves_user_changes_across_worker_restart(tmp_path: Path) -> None:
    config = replace(_build_openclaw_config(tmp_path), tool_mode="worker")
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps(
            {
                "tools": {
                    "agentToAgent": {"enabled": True, "mode": "custom"},
                    "deny": ["browser"],
                }
            }
        ),
        encoding="utf-8",
    )

    worker_runtime = OpenClawRuntime(config)
    worker_runtime.ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))
    payload["tools"]["agentToAgent"]["notes"] = "keep-me"
    payload["tools"]["deny"].append("shell")
    config.config_path.write_text(json.dumps(payload), encoding="utf-8")

    worker_runtime.ensure_layout()
    OpenClawRuntime(replace(config, tool_mode="full")).ensure_layout()

    restored = json.loads(config.config_path.read_text(encoding="utf-8"))
    assert restored["tools"]["agentToAgent"] == {
        "enabled": True,
        "mode": "custom",
        "notes": "keep-me",
    }
    assert restored["tools"]["deny"] == ["browser", "shell"]


def test_openclaw_full_tool_mode_drops_worker_enabled_flag_when_backup_never_had_it(tmp_path: Path) -> None:
    config = replace(_build_openclaw_config(tmp_path), tool_mode="worker")
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps(
            {
                "tools": {
                    "agentToAgent": {"mode": "custom"},
                    "deny": ["browser"],
                }
            }
        ),
        encoding="utf-8",
    )

    worker_runtime = OpenClawRuntime(config)
    worker_runtime.ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))
    payload["tools"]["agentToAgent"]["notes"] = "keep-me"
    config.config_path.write_text(json.dumps(payload), encoding="utf-8")

    OpenClawRuntime(replace(config, tool_mode="full")).ensure_layout()

    restored = json.loads(config.config_path.read_text(encoding="utf-8"))
    assert restored["tools"]["agentToAgent"] == {
        "mode": "custom",
        "notes": "keep-me",
    }


def test_openclaw_full_tool_mode_restores_original_tools_after_unrelated_worker_edits(tmp_path: Path) -> None:
    config = replace(_build_openclaw_config(tmp_path), tool_mode="worker")
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(
        json.dumps(
            {
                "tools": {
                    "agentToAgent": {"enabled": True, "mode": "custom"},
                    "deny": ["browser"],
                },
                "agents": {"main": {"description": "before"}},
            }
        ),
        encoding="utf-8",
    )

    worker_runtime = OpenClawRuntime(config)
    worker_runtime.ensure_layout()

    payload = json.loads(config.config_path.read_text(encoding="utf-8"))
    payload["agents"]["main"]["description"] = "after"
    config.config_path.write_text(json.dumps(payload), encoding="utf-8")

    OpenClawRuntime(replace(config, tool_mode="full")).ensure_layout()

    restored = json.loads(config.config_path.read_text(encoding="utf-8"))
    assert restored["tools"]["agentToAgent"] == {"enabled": True, "mode": "custom"}
    assert restored["tools"]["deny"] == ["browser"]
    assert restored["agents"]["main"]["description"] == "after"

"""Tests for CLI migration helper utilities."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess

import pytest

from agency_swarm.cli import migrate_agent


def _sanitize_name(name: str) -> str:
    """Mirror the generator's sanitizeName helper for assertions."""
    sanitized = re.sub(r"\s+", "_", name)
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "", sanitized)
    sanitized = re.sub(r"_+", "_", sanitized)
    sanitized = sanitized.strip("_")
    if sanitized and sanitized[0].isdigit():
        sanitized = f"agent_{sanitized}"
    return sanitized or "agent"


def test_check_node_dependencies_requires_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure dependency check fails when Node.js is unavailable."""

    def fake_run(command, capture_output, check, shell):  # type: ignore[no-untyped-def]
        raise FileNotFoundError()

    monkeypatch.setattr("agency_swarm.cli.migrate_agent.subprocess.run", fake_run)

    available, runner = migrate_agent.check_node_dependencies()
    assert available is False
    assert runner == ""


def test_check_node_dependencies_requires_ts_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure dependency check fails when tsx/ts-node is unavailable even if Node is present."""

    def fake_run(command, capture_output, check, shell):  # type: ignore[no-untyped-def]
        # Node is available
        if command[0] == "node":
            return CompletedProcess(command, 0)
        # tsx and ts-node are not available
        raise CalledProcessError(1, command)

    monkeypatch.setattr("agency_swarm.cli.migrate_agent.subprocess.run", fake_run)

    available, runner = migrate_agent.check_node_dependencies()
    assert available is False
    assert runner == ""


def test_check_node_dependencies_succeeds_with_tsx(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dependency check should succeed when tsx is available as preferred runner."""

    def fake_run(command, capture_output, check, shell):  # type: ignore[no-untyped-def]
        if command[0] == "node":
            return CompletedProcess(command, 0)
        if command[:2] == ["npx", "tsx"]:
            return CompletedProcess(command, 0)
        raise CalledProcessError(1, command)

    monkeypatch.setattr("agency_swarm.cli.migrate_agent.subprocess.run", fake_run)

    available, runner = migrate_agent.check_node_dependencies()
    assert available is True
    assert runner == "tsx"


def test_check_node_dependencies_succeeds_with_npx_ts_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dependency check should succeed when npx ts-node is available."""

    def fake_run(command, capture_output, check, shell):  # type: ignore[no-untyped-def]
        if command[0] == "node":
            return CompletedProcess(command, 0)
        if command[:2] == ["npx", "tsx"]:
            raise CalledProcessError(1, command)  # tsx not available
        if command[:2] == ["npx", "ts-node"]:
            return CompletedProcess(command, 0)
        raise CalledProcessError(1, command)

    monkeypatch.setattr("agency_swarm.cli.migrate_agent.subprocess.run", fake_run)

    available, runner = migrate_agent.check_node_dependencies()
    assert available is True
    assert runner == "ts-node"


def test_check_node_dependencies_succeeds_with_global_ts_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dependency check should succeed with globally installed ts-node when npx fails."""

    def fake_run(command, capture_output, check, shell):  # type: ignore[no-untyped-def]
        if command[0] == "node":
            return CompletedProcess(command, 0)
        if command[:2] == ["npx", "tsx"]:
            raise CalledProcessError(1, command)  # tsx not available
        if command[:2] == ["npx", "ts-node"]:
            raise CalledProcessError(1, command)  # npx ts-node not available
        if command[0] == "ts-node":
            return CompletedProcess(command, 0)  # global install available
        raise CalledProcessError(1, command)

    monkeypatch.setattr("agency_swarm.cli.migrate_agent.subprocess.run", fake_run)

    available, runner = migrate_agent.check_node_dependencies()
    assert available is True
    assert runner == "ts-node"


def test_find_typescript_script_exists() -> None:
    """The generator script should be discoverable in the package."""
    ts_path = migrate_agent.find_typescript_script()
    assert ts_path is not None
    assert ts_path.exists()
    assert ts_path.name == "generate-agent-from-settings.ts"


def test_migrate_agent_command_missing_settings_returns_error(tmp_path: Path) -> None:
    """Missing settings files should return exit code 1."""
    exit_code = migrate_agent.migrate_agent_command(str(tmp_path / "missing.json"), str(tmp_path))
    assert exit_code == 1


def test_migrate_agent_command_missing_script_returns_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing TypeScript script should return exit code 1."""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}")

    monkeypatch.setattr(migrate_agent, "find_typescript_script", lambda: None)

    exit_code = migrate_agent.migrate_agent_command(str(settings_path), str(tmp_path))
    assert exit_code == 1


def test_migrate_agent_command_dependency_failure_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dependency check failure should return exit code 1."""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}")

    ts_script = tmp_path / "generate-agent-from-settings.ts"
    ts_script.write_text("// stub")

    monkeypatch.setattr(migrate_agent, "find_typescript_script", lambda: ts_script)
    monkeypatch.setattr(migrate_agent, "check_node_dependencies", lambda: (False, ""))

    exit_code = migrate_agent.migrate_agent_command(str(settings_path), str(tmp_path))
    assert exit_code == 1


def test_migrate_agent_command_successful_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful execution should return exit code 0."""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}")

    ts_script = tmp_path / "generate-agent-from-settings.ts"
    ts_script.write_text("// stub")

    monkeypatch.setattr(migrate_agent, "find_typescript_script", lambda: ts_script)
    monkeypatch.setattr(migrate_agent, "check_node_dependencies", lambda: (True, "tsx"))

    completed = CompletedProcess(["npx", "tsx"], 0, stdout="Agent generated successfully\n", stderr="")

    def fake_run(command, capture_output, text, shell):  # type: ignore[no-untyped-def]
        return completed

    monkeypatch.setattr("agency_swarm.cli.migrate_agent.subprocess.run", fake_run)

    exit_code = migrate_agent.migrate_agent_command(str(settings_path), str(tmp_path))
    assert exit_code == 0


def test_migrate_agent_command_failed_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Failed execution should return non-zero exit code."""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}")

    ts_script = tmp_path / "generate-agent-from-settings.ts"
    ts_script.write_text("// stub")

    monkeypatch.setattr(migrate_agent, "find_typescript_script", lambda: ts_script)
    monkeypatch.setattr(migrate_agent, "check_node_dependencies", lambda: (True, "tsx"))

    completed = CompletedProcess(["npx", "tsx"], 2, stdout="", stderr="TypeScript error\n")

    def fake_run(command, capture_output, text, shell):  # type: ignore[no-untyped-def]
        return completed

    monkeypatch.setattr("agency_swarm.cli.migrate_agent.subprocess.run", fake_run)

    exit_code = migrate_agent.migrate_agent_command(str(settings_path), str(tmp_path))
    assert exit_code == 2


def test_generate_agent_script_escapes_strings(tmp_path: Path) -> None:
    """TypeScript generator should escape quotes in user-provided strings."""
    project_root = Path(__file__).parents[2]
    script_path = project_root / "src" / "agency_swarm" / "cli" / "utils" / "generate-agent-from-settings.ts"
    ts_node_binary = project_root / "node_modules" / ".bin" / ("ts-node.cmd" if sys.platform == "win32" else "ts-node")

    if not ts_node_binary.exists():
        pytest.skip("ts-node binary not available for generator test")

    settings = {
        "name": 'Quote "Tester"',
        "description": 'Says "hello" often',
        "instructions": "Be helpful",
        "model": "gpt-5.2",
    }

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps(settings))

    env = os.environ.copy()
    env.setdefault("TS_NODE_TRANSPILE_ONLY", "true")

    subprocess.run(
        [str(ts_node_binary), str(script_path), str(settings_path)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    agent_name = _sanitize_name(settings["name"])
    agent_file = tmp_path / agent_name / f"{agent_name}.py"
    content = agent_file.read_text()

    assert 'name="Quote "Tester""' not in content
    assert 'description="Says "hello" often"' not in content
    assert 'name="Quote \\"Tester\\""' in content
    assert 'description="Says \\"hello\\" often"' in content

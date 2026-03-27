from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from agency_swarm.integrations.openclaw import OpenClawRuntime
from tests.integration.fastapi._openclaw_test_support import _build_openclaw_config


def test_openclaw_start_closes_log_handle_when_popen_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    runtime = OpenClawRuntime(config)
    opened: dict[str, Any] = {}
    original_open = Path.open

    def _tracked_open(path: Path, *args: Any, **kwargs: Any):
        handle = original_open(path, *args, **kwargs)
        if path == runtime.config.log_path:
            opened["handle"] = handle
        return handle

    def _raise_popen(*args: Any, **kwargs: Any):
        raise OSError("spawn failed")

    monkeypatch.setattr(runtime, "_is_port_open", lambda: False)
    monkeypatch.setattr("pathlib.Path.open", _tracked_open)
    monkeypatch.setattr("agency_swarm.integrations.openclaw.subprocess.Popen", _raise_popen)
    monkeypatch.setattr(
        "agency_swarm.integrations.openclaw._select_compatible_node_binary",
        lambda: ("/opt/homebrew/bin/node", (22, 22, 0)),
    )

    with pytest.raises(OSError, match="spawn failed"):
        runtime.start()

    assert runtime._process is None
    assert runtime._log_handle is None
    assert opened["handle"].closed is True


def test_openclaw_failed_startup_cleans_process_and_log_handle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _build_openclaw_config(tmp_path)
    runtime = OpenClawRuntime(replace(config, startup_timeout_seconds=0.01))
    runtime.config.log_path.parent.mkdir(parents=True, exist_ok=True)

    class _FakeProcess:
        def __init__(self) -> None:
            self.pid = 4242
            self.killed = False

        def poll(self) -> int | None:
            return None if not self.killed else -9

        def terminate(self) -> None:
            self.killed = True

        def kill(self) -> None:
            self.killed = True

        def wait(self, timeout: float | None = None) -> int:
            self.killed = True
            return 0

    fake_process = _FakeProcess()

    monkeypatch.setattr(runtime, "ensure_layout", lambda: None)
    monkeypatch.setattr(runtime, "_resolve_gateway_command", lambda: ["openclaw", "gateway"])
    monkeypatch.setattr(runtime, "_merge_provider_keys_from_dotenv", lambda env: None)
    monkeypatch.setattr(runtime, "_is_port_open", lambda: False)
    monkeypatch.setattr("agency_swarm.integrations.openclaw.subprocess.Popen", lambda *a, **k: fake_process)
    monkeypatch.setattr("agency_swarm.integrations.openclaw.os.killpg", lambda pid, sig: fake_process.terminate())
    monkeypatch.setattr("agency_swarm.integrations.openclaw.time.sleep", lambda _delay: None)
    monkeypatch.setattr(
        "agency_swarm.integrations.openclaw._select_compatible_node_binary",
        lambda: ("/opt/homebrew/bin/node", (22, 22, 0)),
    )

    with pytest.raises(TimeoutError):
        runtime.start()

    assert fake_process.killed is True
    assert runtime._process is None
    assert runtime._log_handle is None


def test_openclaw_start_includes_gateway_log_tail_when_process_exits_early(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _build_openclaw_config(tmp_path)
    runtime = OpenClawRuntime(config)
    runtime.config.log_path.parent.mkdir(parents=True, exist_ok=True)
    runtime.config.log_path.write_text("fatal gateway error", encoding="utf-8")

    class _ExitedProcess:
        pid = 4242
        returncode = 1

        def poll(self) -> int | None:
            return 1

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            return 1

    process = _ExitedProcess()

    monkeypatch.setattr(runtime, "ensure_layout", lambda: None)
    monkeypatch.setattr(runtime, "_resolve_gateway_command", lambda: ["openclaw", "gateway"])
    monkeypatch.setattr(runtime, "_merge_provider_keys_from_dotenv", lambda env: None)
    monkeypatch.setattr(runtime, "_is_port_open", lambda: False)
    monkeypatch.setattr("agency_swarm.integrations.openclaw.subprocess.Popen", lambda *a, **k: process)
    monkeypatch.setattr(
        "agency_swarm.integrations.openclaw._select_compatible_node_binary",
        lambda: ("/opt/homebrew/bin/node", (22, 22, 0)),
    )
    monkeypatch.setattr("agency_swarm.integrations.openclaw.time.sleep", lambda _delay: None)

    with pytest.raises(RuntimeError, match="OpenClaw exited early with code 1") as excinfo:
        runtime.start()

    assert "fatal gateway error" in str(excinfo.value)


def test_openclaw_failed_startup_cleanup_closes_log_handle_when_kill_wait_times_out(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _build_openclaw_config(tmp_path)
    runtime = OpenClawRuntime(config)
    runtime.config.log_path.parent.mkdir(parents=True, exist_ok=True)

    class _UnstoppableProcess:
        pid = 4242

        def __init__(self) -> None:
            self.killed = False

        def poll(self) -> int | None:
            return None

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            self.killed = True

        def wait(self, timeout: float | None = None) -> int:
            raise subprocess.TimeoutExpired(cmd="openclaw", timeout=timeout or 0)

    process = _UnstoppableProcess()
    runtime._process = process  # type: ignore[assignment]
    log_handle = config.log_path.open("ab")
    runtime._log_handle = log_handle
    monkeypatch.setattr("agency_swarm.integrations.openclaw.os.killpg", lambda pid, sig: process.kill())

    runtime._cleanup_after_failed_start()

    assert process.killed is True
    assert runtime._process is None
    assert runtime._log_handle is None
    assert log_handle.closed is True


def test_openclaw_stop_forces_kill_on_timeout_and_closes_log_handle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _build_openclaw_config(tmp_path)
    runtime = OpenClawRuntime(config)

    class _SlowProcess:
        pid = 5555

        def __init__(self) -> None:
            self.wait_calls = 0
            self.killed = False

        def poll(self) -> int | None:
            return None

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            self.killed = True

        def wait(self, timeout: float | None = None) -> int:
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise subprocess.TimeoutExpired(cmd="openclaw", timeout=timeout or 0)
            return 0

    process = _SlowProcess()
    runtime._process = process  # type: ignore[assignment]
    config.log_path.parent.mkdir(parents=True, exist_ok=True)
    runtime._log_handle = config.log_path.open("ab")
    monkeypatch.setattr("agency_swarm.integrations.openclaw.os.killpg", lambda pid, sig: process.kill())

    runtime.stop()

    assert process.killed is True
    assert runtime._process is None
    assert runtime._log_handle is None


def test_openclaw_stop_tolerates_second_wait_timeout_after_sigkill(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _build_openclaw_config(tmp_path)
    runtime = OpenClawRuntime(config)

    class _StuckProcess:
        pid = 6000

        def poll(self) -> int | None:
            return None

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            raise subprocess.TimeoutExpired(cmd="openclaw", timeout=timeout or 0)

    process = _StuckProcess()
    runtime._process = process  # type: ignore[assignment]
    config.log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = config.log_path.open("ab")
    runtime._log_handle = log_handle
    monkeypatch.setattr("agency_swarm.integrations.openclaw.os.killpg", lambda pid, sig: process.kill())

    runtime.stop()

    assert runtime._process is None
    assert runtime._log_handle is None
    assert log_handle.closed is True


def test_openclaw_stop_swallows_unexpected_process_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _build_openclaw_config(tmp_path)
    runtime = OpenClawRuntime(config)

    class _RaceProcess:
        pid = 7000

        def poll(self) -> int | None:
            return None

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            return 0

    process = _RaceProcess()
    runtime._process = process  # type: ignore[assignment]
    config.log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = config.log_path.open("ab")
    runtime._log_handle = log_handle

    def _killpg_raise(_pid: int, _sig: int) -> None:
        raise ProcessLookupError("process already exited")

    monkeypatch.setattr("agency_swarm.integrations.openclaw.os.killpg", _killpg_raise)

    runtime.stop()

    assert runtime._process is None
    assert runtime._log_handle is None
    assert log_handle.closed is True

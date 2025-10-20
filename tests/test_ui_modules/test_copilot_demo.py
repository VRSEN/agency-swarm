"""Tests for the Copilot demo launcher."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from agency_swarm.ui.demos.copilot import CopilotDemoLauncher


class DummyProcess:
    def __init__(self) -> None:
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True


def test_copilot_demo_requires_npm(monkeypatch: pytest.MonkeyPatch) -> None:
    """An informative error should be raised when npm is unavailable."""
    monkeypatch.setattr("shutil.which", lambda _: None)

    with pytest.raises(RuntimeError) as exc_info:
        CopilotDemoLauncher.start(SimpleNamespace(name="demo"))

    assert "npm was not found" in str(exc_info.value)


def test_copilot_demo_installs_dependencies_and_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing node_modules should trigger installation and FastAPI startup."""
    frontend_dir = tmp_path / "copilot"
    frontend_dir.mkdir()

    monkeypatch.setattr("agency_swarm.ui.demos.copilot.__file__", str(tmp_path / "launcher_stub.py"))
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/npm")

    install_calls: list[list[str]] = []
    popen_calls: list[list[str]] = []
    atexit_handlers: list[Callable[[], None]] = []
    fastapi_invocations: list[dict[str, object]] = []

    def fake_check_call(cmd, cwd):
        install_calls.append(cmd)
        assert cwd == frontend_dir

    def fake_popen(cmd, cwd, stdout, stderr):
        popen_calls.append(cmd)
        assert cwd == frontend_dir
        return DummyProcess()

    def fake_atexit(handler):
        atexit_handlers.append(handler)

    def fake_run_fastapi(**kwargs):
        fastapi_invocations.append(kwargs)

    monkeypatch.setattr("subprocess.check_call", fake_check_call)
    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.setattr("atexit.register", fake_atexit)
    monkeypatch.setattr("agency_swarm.integrations.fastapi.run_fastapi", fake_run_fastapi)

    # Ensure downstream mutations do not leak into the real environment
    original_env = os.environ.copy()
    try:
        CopilotDemoLauncher.start(
            SimpleNamespace(name="demo"),
            host="127.0.0.1",
            port=9000,
            frontend_port=3100,
            cors_origins=["*"],
        )
        backend_url = os.environ.get("NEXT_PUBLIC_AG_UI_BACKEND_URL")
    finally:
        os.environ.clear()
        os.environ.update(original_env)

    assert install_calls == [["/usr/bin/npm", "install"]]
    assert popen_calls == [["/usr/bin/npm", "run", "dev", "--", "-p", "3100"]]
    assert atexit_handlers, "Process termination handler should be registered"
    assert backend_url == "http://127.0.0.1:9000/demo/get_response_stream/"
    assert fastapi_invocations and fastapi_invocations[0]["enable_agui"] is True

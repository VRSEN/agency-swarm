import importlib
import json
import subprocess

from agency_swarm import Agency, Agent

opencode_demo = importlib.import_module("agency_swarm.ui.demos.opencode")


class DummyServer:
    def __init__(self, port: int = 43121) -> None:
        self.port = port
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def build_agency() -> Agency:
    return Agency(Agent(name="CEO", instructions="test"), name="My Agency")


def test_opencode_terminal_demo_launches_agency_code(monkeypatch):
    agency = build_agency()
    server = DummyServer()
    calls: dict[str, object] = {}

    monkeypatch.delenv(opencode_demo._LEGACY_ENV, raising=False)
    monkeypatch.delenv(opencode_demo._RELOAD_CHILD_ENV, raising=False)
    monkeypatch.setattr(opencode_demo.os, "getcwd", lambda: "/tmp/project")
    monkeypatch.setattr(opencode_demo, "_start_server", lambda value: server)
    monkeypatch.setattr(opencode_demo.shutil, "which", lambda _: "/usr/local/bin/agency")

    def fake_run(cmd, cwd, env, check):
        calls["cmd"] = cmd
        calls["cwd"] = cwd
        calls["env"] = env
        calls["check"] = check
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(opencode_demo.subprocess, "run", fake_run)

    opencode_demo.start_terminal(agency, reload=False)

    assert calls["cmd"] == ["/usr/local/bin/agency", "--model", opencode_demo._MODEL]
    assert calls["cwd"] == "/tmp/project"
    assert calls["check"] is False
    config = json.loads(calls["env"]["OPENCODE_CONFIG_CONTENT"])
    assert config["model"] == opencode_demo._MODEL
    assert config["provider"]["agency-swarm"]["options"]["baseURL"] == "http://127.0.0.1:43121"
    assert config["provider"]["agency-swarm"]["options"]["agency"] == "My_Agency"
    assert server.stopped is True


def test_opencode_terminal_demo_continues_after_reload(monkeypatch):
    agency = build_agency()
    server = DummyServer()
    calls: list[str] = []

    monkeypatch.setenv(opencode_demo._RELOAD_CHILD_ENV, "1")
    monkeypatch.setattr(opencode_demo.os, "getcwd", lambda: "/tmp/project")
    monkeypatch.setattr(opencode_demo, "_start_server", lambda value: server)
    monkeypatch.setattr(opencode_demo.shutil, "which", lambda _: "/usr/local/bin/agency")
    monkeypatch.setattr(
        opencode_demo.subprocess,
        "run",
        lambda cmd, cwd, env, check: calls.extend(cmd) or subprocess.CompletedProcess(cmd, 0),
    )

    opencode_demo.start_terminal(agency, reload=False)

    assert "--continue" in calls
    assert server.stopped is True


def test_opencode_terminal_demo_falls_back_when_cli_missing(monkeypatch):
    agency = build_agency()
    calls: list[tuple[Agency, bool | None, bool]] = []

    monkeypatch.delenv(opencode_demo._LEGACY_ENV, raising=False)
    monkeypatch.setattr(opencode_demo.shutil, "which", lambda _: None)
    monkeypatch.setattr(
        opencode_demo,
        "start_legacy_terminal",
        lambda value, show_reasoning, reload: calls.append((value, show_reasoning, reload)),
    )

    opencode_demo.start_terminal(agency, reload=False)

    assert calls == [(agency, None, False)]


def test_opencode_terminal_demo_falls_back_when_reasoning_hidden(monkeypatch):
    agency = build_agency()
    calls: list[tuple[Agency, bool | None, bool]] = []

    monkeypatch.setattr(
        opencode_demo,
        "start_legacy_terminal",
        lambda value, show_reasoning, reload: calls.append((value, show_reasoning, reload)),
    )

    opencode_demo.start_terminal(agency, show_reasoning=False, reload=False)

    assert calls == [(agency, False, False)]

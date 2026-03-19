import importlib
import json
import subprocess

import pytest

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


def test_opencode_terminal_demo_launches_agent_swarm_cli(monkeypatch):
    agency = build_agency()
    server = DummyServer()
    calls: dict[str, object] = {}

    monkeypatch.delenv(opencode_demo._RELOAD_CHILD_ENV, raising=False)
    monkeypatch.setattr(opencode_demo.os, "getcwd", lambda: "/tmp/project")
    monkeypatch.setattr(opencode_demo, "_start_server", lambda value: server)
    monkeypatch.setattr(
        opencode_demo.shutil,
        "which",
        lambda value: "/usr/local/bin/agentswarm" if value == "agentswarm" else None,
    )

    def fake_run(cmd, cwd, env, check):
        calls["cmd"] = cmd
        calls["cwd"] = cwd
        calls["env"] = env
        calls["check"] = check
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(opencode_demo.subprocess, "run", fake_run)

    opencode_demo.start_terminal(agency, reload=False)

    assert calls["cmd"] == ["/usr/local/bin/agentswarm", "--model", opencode_demo._MODEL]
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
    monkeypatch.setattr(
        opencode_demo.shutil,
        "which",
        lambda value: "/usr/local/bin/agentswarm" if value == "agentswarm" else None,
    )
    monkeypatch.setattr(
        opencode_demo.subprocess,
        "run",
        lambda cmd, cwd, env, check: calls.extend(cmd) or subprocess.CompletedProcess(cmd, 0),
    )

    opencode_demo.start_terminal(agency, reload=False)

    assert "--continue" in calls
    assert server.stopped is True


def test_opencode_terminal_demo_requires_agent_swarm_cli(monkeypatch):
    agency = build_agency()

    monkeypatch.setattr(opencode_demo.shutil, "which", lambda _: None)

    with pytest.raises(RuntimeError, match="Install it with `npm i -g agentswarm-cli`"):
        opencode_demo.start_terminal(agency, reload=False)


def test_opencode_terminal_demo_rejects_hidden_reasoning():
    agency = build_agency()

    with pytest.raises(NotImplementedError, match="show_reasoning=False"):
        opencode_demo.start_terminal(agency, show_reasoning=False, reload=False)


def test_opencode_terminal_demo_raises_when_bridge_fails(monkeypatch):
    agency = build_agency()

    monkeypatch.setattr(
        opencode_demo.shutil,
        "which",
        lambda value: "/usr/local/bin/agentswarm" if value == "agentswarm" else None,
    )
    monkeypatch.setattr(opencode_demo, "_start_server", lambda value: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="bridge failed to start"):
        opencode_demo.start_terminal(agency, reload=False)


def test_opencode_terminal_demo_raises_when_cli_launch_fails(monkeypatch):
    agency = build_agency()
    server = DummyServer()

    monkeypatch.setattr(opencode_demo.os, "getcwd", lambda: "/tmp/project")
    monkeypatch.setattr(opencode_demo, "_start_server", lambda value: server)
    monkeypatch.setattr(
        opencode_demo.shutil,
        "which",
        lambda value: "/usr/local/bin/agentswarm" if value == "agentswarm" else None,
    )
    monkeypatch.setattr(opencode_demo.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("boom")))

    with pytest.raises(RuntimeError, match="could not be launched"):
        opencode_demo.start_terminal(agency, reload=False)

    assert server.stopped is True

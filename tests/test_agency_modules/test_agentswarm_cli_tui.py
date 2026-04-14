import importlib
import json
import subprocess
import tarfile
from io import BytesIO
from pathlib import Path

import pytest

from agency_swarm import Agency, Agent

agentswarm_cli_demo = importlib.import_module("agency_swarm.ui.demos.agentswarm_cli")


class DummyServer:
    def __init__(self, port: int = 43121) -> None:
        self.port = port
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def build_agency() -> Agency:
    return Agency(Agent(name="CEO", instructions="test"), name="My Agency")


def test_agentswarm_cli_tui_launches_agent_swarm_cli(monkeypatch):
    agency = build_agency()
    server = DummyServer()
    calls: dict[str, object] = {}

    monkeypatch.delenv(agentswarm_cli_demo._RELOAD_CHILD_ENV, raising=False)
    monkeypatch.setattr(agentswarm_cli_demo.os, "getcwd", lambda: "/tmp/project")
    monkeypatch.setattr(agentswarm_cli_demo, "_start_server", lambda value: server)
    monkeypatch.setattr(agentswarm_cli_demo, "_ensure_cli", lambda: Path("/usr/local/bin/agentswarm"))

    def fake_run(cmd, cwd, env, check):
        calls["cmd"] = cmd
        calls["cwd"] = cwd
        calls["env"] = env
        calls["check"] = check
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(agentswarm_cli_demo.subprocess, "run", fake_run)

    agentswarm_cli_demo.start_tui(agency, reload=False)

    assert calls["cmd"] == ["/usr/local/bin/agentswarm", "--model", agentswarm_cli_demo._MODEL]
    assert calls["cwd"] == "/tmp/project"
    assert calls["check"] is False
    config = json.loads(calls["env"]["OPENCODE_CONFIG_CONTENT"])
    assert config["model"] == agentswarm_cli_demo._MODEL
    assert config["provider"]["agency-swarm"]["options"]["baseURL"] == "http://127.0.0.1:43121"
    assert config["provider"]["agency-swarm"]["options"]["agency"] == "My_Agency"
    assert server.stopped is True


def test_agentswarm_cli_tui_continues_after_reload(monkeypatch):
    agency = build_agency()
    server = DummyServer()
    calls: list[str] = []

    monkeypatch.setenv(agentswarm_cli_demo._RELOAD_CHILD_ENV, "1")
    monkeypatch.setattr(agentswarm_cli_demo.os, "getcwd", lambda: "/tmp/project")
    monkeypatch.setattr(agentswarm_cli_demo, "_start_server", lambda value: server)
    monkeypatch.setattr(agentswarm_cli_demo, "_ensure_cli", lambda: Path("/usr/local/bin/agentswarm"))
    monkeypatch.setattr(
        agentswarm_cli_demo.subprocess,
        "run",
        lambda cmd, cwd, env, check: calls.extend(cmd) or subprocess.CompletedProcess(cmd, 0),
    )

    agentswarm_cli_demo.start_tui(agency, reload=False)

    assert "--continue" in calls
    assert server.stopped is True


def test_agentswarm_cli_tui_installs_agent_swarm_cli(monkeypatch):
    monkeypatch.delenv(agentswarm_cli_demo._BIN_ENV, raising=False)
    monkeypatch.setattr(agentswarm_cli_demo, "_ensure_cli", lambda: Path("/tmp/cache/agentswarm"))

    assert agentswarm_cli_demo._command() == ["/tmp/cache/agentswarm"]


def test_agentswarm_cli_tui_prefers_explicit_cli(monkeypatch):
    monkeypatch.setenv(agentswarm_cli_demo._BIN_ENV, "/tmp/agentswarm")
    monkeypatch.setattr(agentswarm_cli_demo, "_ensure_cli", lambda: (_ for _ in ()).throw(AssertionError("unused")))

    assert agentswarm_cli_demo._command() == ["/tmp/agentswarm"]


def test_agentswarm_cli_tui_rejects_hidden_reasoning():
    agency = build_agency()

    with pytest.raises(NotImplementedError, match="show_reasoning=False"):
        agentswarm_cli_demo.start_tui(agency, show_reasoning=False, reload=False)


def test_agentswarm_cli_tui_raises_when_bridge_fails(monkeypatch):
    agency = build_agency()

    monkeypatch.setattr(agentswarm_cli_demo, "_ensure_cli", lambda: Path("/usr/local/bin/agentswarm"))
    monkeypatch.setattr(agentswarm_cli_demo, "_start_server", lambda value: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="bridge failed to start"):
        agentswarm_cli_demo.start_tui(agency, reload=False)


def test_agentswarm_cli_tui_raises_when_cli_launch_fails(monkeypatch):
    agency = build_agency()
    server = DummyServer()

    monkeypatch.setattr(agentswarm_cli_demo.os, "getcwd", lambda: "/tmp/project")
    monkeypatch.setattr(agentswarm_cli_demo, "_start_server", lambda value: server)
    monkeypatch.setattr(agentswarm_cli_demo, "_ensure_cli", lambda: Path("/usr/local/bin/agentswarm"))
    monkeypatch.setattr(
        agentswarm_cli_demo.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("boom")),
    )

    with pytest.raises(RuntimeError, match="could not be launched"):
        agentswarm_cli_demo.start_tui(agency, reload=False)

    assert server.stopped is True


def test_agentswarm_cli_tui_downloads_platform_cli(monkeypatch, tmp_path):
    root = tmp_path / "cache"
    blob = BytesIO()
    with tarfile.open(fileobj=blob, mode="w:gz") as tar:
        data = b"#!/bin/sh\nexit 0\n"
        info = tarfile.TarInfo("package/bin/agentswarm")
        info.size = len(data)
        info.mode = 0o755
        tar.addfile(info, BytesIO(data))
    data = blob.getvalue()
    sha = agentswarm_cli_demo.hashlib.sha1(data).hexdigest()
    calls: list[str] = []

    class Response:
        def __init__(self, payload=None, chunks=None):
            self.payload = payload
            self.chunks = chunks or []

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

        def iter_content(self, chunk_size=0):
            return iter(self.chunks)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_get(url, timeout, stream=False):
        calls.append(url)
        if stream:
            return Response(chunks=[data])
        return Response(
            payload={
                "dist": {
                    "tarball": "https://registry.npmjs.org/@vrsen/agentswarm-cli-darwin-arm64/-/pkg.tgz",
                    "shasum": sha,
                }
            }
        )

    monkeypatch.setattr(agentswarm_cli_demo.requests, "get", fake_get)
    monkeypatch.setattr(agentswarm_cli_demo, "_cache", lambda: root)
    monkeypatch.setattr(
        agentswarm_cli_demo,
        "_package",
        lambda: agentswarm_cli_demo._Package(
            "agentswarm-cli-darwin-arm64",
            "agentswarm",
            "@vrsen/agentswarm-cli-darwin-arm64",
        ),
    )
    monkeypatch.setattr(agentswarm_cli_demo, "_CLI_VERSION", "1.2.27-test")

    path = agentswarm_cli_demo._ensure_cli()

    assert path == root / "1.2.27-test" / "agentswarm-cli-darwin-arm64" / "agentswarm"
    assert path.read_text() == "#!/bin/sh\nexit 0\n"
    assert calls == [
        "https://registry.npmjs.org/%40vrsen%2Fagentswarm-cli-darwin-arm64/1.2.27-test",
        "https://registry.npmjs.org/@vrsen/agentswarm-cli-darwin-arm64/-/pkg.tgz",
    ]


def test_agentswarm_cli_tui_notifies_on_first_run(monkeypatch, tmp_path):
    root = tmp_path / "cache"
    notices: list[str] = []

    monkeypatch.setattr(agentswarm_cli_demo, "_cache", lambda: root)
    monkeypatch.setattr(
        agentswarm_cli_demo,
        "_package",
        lambda: agentswarm_cli_demo._Package(
            "agentswarm-cli-darwin-arm64",
            "agentswarm",
            "@vrsen/agentswarm-cli-darwin-arm64",
        ),
    )
    monkeypatch.setattr(agentswarm_cli_demo, "_install", lambda pkg, install_root, path: path.write_text("ok"))
    monkeypatch.setattr(agentswarm_cli_demo, "_notify_setup", notices.append)

    path = agentswarm_cli_demo._ensure_cli()

    assert path.read_text() == "ok"
    assert notices == [
        agentswarm_cli_demo._SETUP_MESSAGE,
        agentswarm_cli_demo._SETUP_COMPLETE_MESSAGE,
    ]

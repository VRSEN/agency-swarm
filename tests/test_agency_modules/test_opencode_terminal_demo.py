import importlib
import json
import subprocess
import tarfile
from io import BytesIO
from pathlib import Path

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
    monkeypatch.setattr(opencode_demo, "_ensure_cli", lambda: Path("/usr/local/bin/agentswarm"))

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
    monkeypatch.setattr(opencode_demo, "_ensure_cli", lambda: Path("/usr/local/bin/agentswarm"))
    monkeypatch.setattr(
        opencode_demo.subprocess,
        "run",
        lambda cmd, cwd, env, check: calls.extend(cmd) or subprocess.CompletedProcess(cmd, 0),
    )

    opencode_demo.start_terminal(agency, reload=False)

    assert "--continue" in calls
    assert server.stopped is True


def test_opencode_terminal_demo_installs_agent_swarm_cli(monkeypatch):
    monkeypatch.delenv(opencode_demo._BIN_ENV, raising=False)
    monkeypatch.setattr(opencode_demo, "_ensure_cli", lambda: Path("/tmp/cache/agentswarm"))

    assert opencode_demo._command() == ["/tmp/cache/agentswarm"]


def test_opencode_terminal_demo_prefers_explicit_cli(monkeypatch):
    monkeypatch.setenv(opencode_demo._BIN_ENV, "/tmp/agentswarm")
    monkeypatch.setattr(opencode_demo, "_ensure_cli", lambda: (_ for _ in ()).throw(AssertionError("unused")))

    assert opencode_demo._command() == ["/tmp/agentswarm"]


def test_opencode_terminal_demo_rejects_hidden_reasoning():
    agency = build_agency()

    with pytest.raises(NotImplementedError, match="show_reasoning=False"):
        opencode_demo.start_terminal(agency, show_reasoning=False, reload=False)


def test_opencode_terminal_demo_raises_when_bridge_fails(monkeypatch):
    agency = build_agency()

    monkeypatch.setattr(opencode_demo, "_ensure_cli", lambda: Path("/usr/local/bin/agentswarm"))
    monkeypatch.setattr(opencode_demo, "_start_server", lambda value: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="bridge failed to start"):
        opencode_demo.start_terminal(agency, reload=False)


def test_opencode_terminal_demo_raises_when_cli_launch_fails(monkeypatch):
    agency = build_agency()
    server = DummyServer()

    monkeypatch.setattr(opencode_demo.os, "getcwd", lambda: "/tmp/project")
    monkeypatch.setattr(opencode_demo, "_start_server", lambda value: server)
    monkeypatch.setattr(opencode_demo, "_ensure_cli", lambda: Path("/usr/local/bin/agentswarm"))
    monkeypatch.setattr(opencode_demo.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("boom")))

    with pytest.raises(RuntimeError, match="could not be launched"):
        opencode_demo.start_terminal(agency, reload=False)

    assert server.stopped is True


def test_opencode_terminal_demo_downloads_platform_cli(monkeypatch, tmp_path):
    root = tmp_path / "cache"
    blob = BytesIO()
    with tarfile.open(fileobj=blob, mode="w:gz") as tar:
        data = b"#!/bin/sh\nexit 0\n"
        info = tarfile.TarInfo("package/bin/agency")
        info.size = len(data)
        info.mode = 0o755
        tar.addfile(info, BytesIO(data))
    data = blob.getvalue()
    sha = opencode_demo.hashlib.sha1(data).hexdigest()
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
                    "tarball": "https://registry.npmjs.org/agent-swarm-cli-darwin-arm64/-/pkg.tgz",
                    "shasum": sha,
                }
            }
        )

    monkeypatch.setattr(opencode_demo.requests, "get", fake_get)
    monkeypatch.setattr(opencode_demo, "_cache", lambda: root)
    monkeypatch.setattr(
        opencode_demo,
        "_package",
        lambda: opencode_demo._Package("agent-swarm-cli-darwin-arm64", "agency"),
    )
    monkeypatch.setattr(opencode_demo, "_CLI_VERSION", "1.2.27-test")

    path = opencode_demo._ensure_cli()

    assert path == root / "1.2.27-test" / "agent-swarm-cli-darwin-arm64" / "agency"
    assert path.read_text() == "#!/bin/sh\nexit 0\n"
    assert calls == [
        "https://registry.npmjs.org/agent-swarm-cli-darwin-arm64/1.2.27-test",
        "https://registry.npmjs.org/agent-swarm-cli-darwin-arm64/-/pkg.tgz",
    ]

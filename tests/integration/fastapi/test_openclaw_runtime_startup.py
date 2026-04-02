from __future__ import annotations

import subprocess
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi.testclient")
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from agency_swarm.integrations import openclaw as openclaw_mod
from agency_swarm.integrations.openclaw import (
    OpenClawIntegrationConfig,
    OpenClawRuntime,
    attach_openclaw_to_fastapi,
    normalize_openclaw_responses_request,
)
from tests.integration.fastapi._openclaw_test_support import _build_openclaw_config


def test_openclaw_runtime_uses_lifespan_hooks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    runtime = attach_openclaw_to_fastapi(app, replace(_build_openclaw_config(tmp_path), autostart=True))
    calls = {"start": 0, "stop": 0}
    to_thread_calls: list[str] = []

    def _start() -> None:
        calls["start"] += 1

    def _stop() -> None:
        calls["stop"] += 1

    async def _to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
        to_thread_calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(runtime, "start", _start)
    monkeypatch.setattr(runtime, "stop", _stop)
    monkeypatch.setattr(openclaw_mod.asyncio, "to_thread", _to_thread)

    with TestClient(app):
        assert calls == {"start": 1, "stop": 0}

    assert calls == {"start": 1, "stop": 1}
    assert to_thread_calls == ["_start", "_stop"]


def test_openclaw_lifespan_preserves_existing_state(tmp_path: Path) -> None:
    @asynccontextmanager
    async def _existing_lifespan(_app: FastAPI):
        yield {"existing_marker": "kept"}

    app = FastAPI(lifespan=_existing_lifespan)
    attach_openclaw_to_fastapi(app, replace(_build_openclaw_config(tmp_path), autostart=False))

    @app.get("/state-marker")
    async def state_marker(request: Request) -> dict[str, str]:
        return {"existing_marker": request.state.existing_marker}

    with TestClient(app) as client:
        response = client.get("/state-marker")

    assert response.status_code == 200
    assert response.json() == {"existing_marker": "kept"}


def test_openclaw_runtime_does_not_stop_when_autostart_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = FastAPI()
    runtime = attach_openclaw_to_fastapi(app, replace(_build_openclaw_config(tmp_path), autostart=False))
    calls = {"stop": 0}
    to_thread_calls: list[str] = []

    def _stop() -> None:
        calls["stop"] += 1

    async def _to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
        to_thread_calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(runtime, "stop", _stop)
    monkeypatch.setattr(openclaw_mod.asyncio, "to_thread", _to_thread)

    with TestClient(app):
        pass

    assert calls == {"stop": 0}
    assert to_thread_calls == []


def test_openclaw_port_probe_supports_ipv6(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = replace(_build_openclaw_config(tmp_path), host="::1")

    class _FakeSocket:
        def __init__(self, family: int, _socktype: int, _proto: int) -> None:
            self.family = family

        def __enter__(self) -> _FakeSocket:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def settimeout(self, _timeout: float) -> None:
            return None

        def connect(self, _sockaddr: Any) -> None:
            if self.family == openclaw_mod.socket.AF_INET6:
                return None
            raise OSError("unreachable")

    monkeypatch.setattr(
        openclaw_mod.socket,
        "getaddrinfo",
        lambda _host, _port, type: [
            (openclaw_mod.socket.AF_INET, openclaw_mod.socket.SOCK_STREAM, 0, "", ("127.0.0.1", config.port)),
            (openclaw_mod.socket.AF_INET6, openclaw_mod.socket.SOCK_STREAM, 0, "", ("::1", config.port, 0, 0)),
        ],
    )
    monkeypatch.setattr(openclaw_mod.socket, "socket", _FakeSocket)

    assert openclaw_mod._is_upstream_port_open(config) is True


def test_openclaw_upstream_base_url_brackets_ipv6_host(tmp_path: Path) -> None:
    config = replace(_build_openclaw_config(tmp_path), host="::1")
    assert config.upstream_base_url == "http://[::1]:18789"


def test_openclaw_gateway_command_port_detection_supports_equals_syntax(tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    runtime = OpenClawRuntime(replace(config, port=19000, gateway_command="openclaw gateway --port=19000"))

    command = runtime._resolve_gateway_command()
    port_args = [arg for arg in command if arg == "--port" or arg.startswith("--port=")]
    assert port_args == ["--port=19000"]


def test_openclaw_gateway_command_rejects_invalid_port_value(tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    runtime = OpenClawRuntime(replace(config, gateway_command="openclaw gateway --port=abc"))

    with pytest.raises(RuntimeError, match="Invalid OPENCLAW_GATEWAY_COMMAND --port value"):
        runtime._resolve_gateway_command()


def test_openclaw_gateway_command_rejects_port_mismatch(tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    runtime = OpenClawRuntime(replace(config, port=18789, gateway_command="openclaw gateway --port=19000"))

    with pytest.raises(RuntimeError, match="does not match configured OPENCLAW_PORT"):
        runtime._resolve_gateway_command()


def test_openclaw_config_from_env_prefers_gateway_command_port(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OPENCLAW_PORT", "18789")
    monkeypatch.setenv("OPENCLAW_GATEWAY_COMMAND", "openclaw gateway --port=19000")

    config = OpenClawIntegrationConfig.from_env()

    assert config.port == 19000
    assert config.upstream_base_url == "http://127.0.0.1:19000"


def test_openclaw_start_fails_when_port_is_already_in_use(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    runtime = OpenClawRuntime(config)

    monkeypatch.setattr(runtime, "_is_port_open", lambda: True)

    with pytest.raises(RuntimeError, match="already in use"):
        runtime.start()


def test_openclaw_metadata_validation_rejects_non_json_serializable_values() -> None:
    with pytest.raises(ValueError, match="metadata\\['bad'\\] must be JSON-serializable"):
        normalize_openclaw_responses_request(
            {
                "model": "openclaw:main",
                "input": "hello",
                "metadata": {"bad": {1, 2}},
            }
        )


def test_openclaw_from_env_handles_boolean_and_unparseable_gateway_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OPENCLAW_AUTOSTART", "false")
    monkeypatch.setenv("OPENCLAW_GATEWAY_COMMAND", 'openclaw gateway --port "broken')
    monkeypatch.setenv("OPENCLAW_PORT", "19001")

    config = OpenClawIntegrationConfig.from_env()

    assert config.autostart is False
    assert config.port == 19001
    assert config.gateway_command == 'openclaw gateway --port "broken'


def test_openclaw_from_env_defaults_gateway_token_to_app_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("APP_TOKEN", "app-token")
    monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN", raising=False)

    config = OpenClawIntegrationConfig.from_env()

    assert config.gateway_token == "app-token"


def test_openclaw_from_env_defaults_gateway_token_to_local_value_when_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN", raising=False)
    monkeypatch.delenv("APP_TOKEN", raising=False)

    config = OpenClawIntegrationConfig.from_env()

    assert config.gateway_token == "openclaw-local-token"


def test_openclaw_extract_port_parser_handles_edge_values() -> None:
    assert openclaw_mod._extract_port_from_gateway_command(["openclaw", "gateway", "--port", "19000"]) == 19000
    assert openclaw_mod._extract_port_from_gateway_command(["openclaw", "gateway", "--port=19000"]) == 19000
    assert openclaw_mod._extract_port_from_gateway_command(["openclaw", "gateway", "--port"]) is None
    assert openclaw_mod._extract_port_from_gateway_command(["openclaw", "gateway", "--port=abc"]) is None
    assert openclaw_mod._extract_port_from_gateway_command(["openclaw", "gateway", "--port=70000"]) is None


def test_openclaw_select_compatible_node_binary_prefers_explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCLAW_NODE_BIN", "/custom/node")

    def _fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        binary = command[0]
        versions = {
            "/custom/node": "v22.12.1\n",
            "/tmp/path-node": "v20.18.3\n",
        }
        if binary in versions:
            return subprocess.CompletedProcess(command, 0, versions[binary], "")
        raise FileNotFoundError(binary)

    monkeypatch.setattr(openclaw_mod.shutil, "which", lambda name: "/tmp/path-node" if name == "node" else None)
    monkeypatch.setattr(openclaw_mod.subprocess, "run", _fake_run)

    binary, version = openclaw_mod._select_compatible_node_binary()

    assert binary == "/custom/node"
    assert version == (22, 12, 1)


def test_openclaw_select_compatible_node_binary_uses_fallback_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCLAW_NODE_BIN", raising=False)

    def _fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        binary = command[0]
        versions = {
            "/tmp/path-node": "v20.18.3\n",
            "/opt/homebrew/bin/node": "v22.22.0\n",
            "/usr/local/bin/node": "v18.20.0\n",
        }
        if binary in versions:
            return subprocess.CompletedProcess(command, 0, versions[binary], "")
        raise FileNotFoundError(binary)

    monkeypatch.setattr(openclaw_mod.shutil, "which", lambda name: "/tmp/path-node" if name == "node" else None)
    monkeypatch.setattr(openclaw_mod.subprocess, "run", _fake_run)

    binary, version = openclaw_mod._select_compatible_node_binary()

    assert binary == "/opt/homebrew/bin/node"
    assert version == (22, 22, 0)


def test_openclaw_select_compatible_node_binary_reports_highest_detected_when_incompatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENCLAW_NODE_BIN", raising=False)

    def _fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        binary = command[0]
        versions = {
            "/tmp/path-node": "v20.18.3\n",
            "/opt/homebrew/bin/node": "v21.9.0\n",
            "/usr/local/bin/node": "v19.4.0\n",
        }
        if binary in versions:
            return subprocess.CompletedProcess(command, 0, versions[binary], "")
        raise FileNotFoundError(binary)

    monkeypatch.setattr(openclaw_mod.shutil, "which", lambda name: "/tmp/path-node" if name == "node" else None)
    monkeypatch.setattr(openclaw_mod.subprocess, "run", _fake_run)

    binary, version = openclaw_mod._select_compatible_node_binary()

    assert binary is None
    assert version == (21, 9, 0)


def test_openclaw_merge_provider_keys_from_dotenv_loads_only_missing_keys(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dotenv_path = tmp_path / "openclaw.env"
    dotenv_path.write_text(
        "OPENAI_API_KEY=from_dotenv\nANTHROPIC_API_KEY=anthropic_dotenv\nIGNORED=value\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENCLAW_DOTENV_PATH", str(dotenv_path))

    runtime = OpenClawRuntime(_build_openclaw_config(tmp_path))
    env = {"OPENAI_API_KEY": "already_set"}

    runtime._merge_provider_keys_from_dotenv(env)

    assert env["OPENAI_API_KEY"] == "already_set"
    assert env["ANTHROPIC_API_KEY"] == "anthropic_dotenv"
    assert "IGNORED" not in env


def test_openclaw_resolve_gateway_command_errors_when_binary_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = replace(_build_openclaw_config(tmp_path), gateway_command=None)
    runtime = OpenClawRuntime(config)
    monkeypatch.setattr("agency_swarm.integrations.openclaw.shutil.which", lambda _name: None)

    with pytest.raises(RuntimeError, match="OpenClaw runtime unavailable"):
        runtime._resolve_gateway_command()


def test_openclaw_resolve_gateway_command_reports_invalid_shell_quoting(tmp_path: Path) -> None:
    runtime = OpenClawRuntime(
        replace(_build_openclaw_config(tmp_path), gateway_command='openclaw gateway --port "broken')
    )

    with pytest.raises(RuntimeError, match="Invalid OPENCLAW_GATEWAY_COMMAND"):
        runtime._resolve_gateway_command()

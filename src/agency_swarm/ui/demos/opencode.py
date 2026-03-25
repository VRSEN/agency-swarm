from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypedDict

import requests

from agency_swarm.agency.helpers import build_fastapi_agencies
from agency_swarm.integrations.fastapi import run_fastapi
from agency_swarm.ui.demos.terminal import (
    _RELOAD_CHILD_ENV,
    TerminalReloader,
    _get_caller_script_path,
    _get_watch_directory,
)

logger = logging.getLogger(__name__)

_BIN_ENV = "AGENTSWARM_BIN"
_ARGS_ENV = "AGENCY_SWARM_OPENCODE_ARGS"
_HOST = "127.0.0.1"
_MODEL = "agency-swarm/default"
_CLI_VERSION = "1.2.27"
_CLI_REGISTRY = "https://registry.npmjs.org"
_LOCK_AGE = 300
_LOCK_WAIT = 30


@dataclass(frozen=True)
class _Package:
    name: str
    binary: str


class _Dist(TypedDict):
    tarball: str
    shasum: str | None


class _Meta(TypedDict):
    dist: _Dist


class _UvicornServer(Protocol):
    should_exit: bool
    started: bool

    def run(self) -> None: ...


@dataclass
class _Server:
    port: int
    server: _UvicornServer
    thread: threading.Thread

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)


def start_terminal(agency, show_reasoning: bool | None = None, reload: bool = True) -> None:
    """Launch the Agent Swarm CLI terminal for a live agency instance."""
    if show_reasoning is False:
        raise NotImplementedError("terminal_demo(show_reasoning=False) is not supported in the new TUI yet.")

    if reload and not os.environ.get(_RELOAD_CHILD_ENV):
        script_path = _get_caller_script_path()
        if script_path is not None:
            TerminalReloader(script_path, _get_watch_directory(script_path)).run()
            return
        logger.warning("Could not determine script path for hot reload. Running without reload.")

    command = _command()

    try:
        server = _start_server(agency)
    except Exception as exc:
        raise RuntimeError("Agent Swarm CLI bridge failed to start.") from exc

    try:
        result = subprocess.run(
            [*command, *_command_args()],
            cwd=os.getcwd(),
            env=_env(server.port, _agency_id(agency)),
            check=False,
        )
    except OSError as exc:
        raise RuntimeError("Agent Swarm CLI could not be launched.") from exc
    finally:
        server.stop()

    if result.returncode not in (0, 130):
        raise subprocess.CalledProcessError(result.returncode, [*command, *_command_args()])


def _command() -> list[str]:
    explicit = os.environ.get(_BIN_ENV)
    if explicit:
        return [explicit]
    return [str(_ensure_cli())]


def _command_args() -> list[str]:
    args = ["--model", _MODEL]
    if os.environ.get(_RELOAD_CHILD_ENV) == "1":
        args.append("--continue")
    extra = os.environ.get(_ARGS_ENV)
    if extra:
        args.extend(shlex.split(extra))
    return args


def _env(port: int, agency_id: str) -> dict[str, str]:
    env = os.environ.copy()
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(
        {
            "$schema": "https://opencode.ai/config.json",
            "model": _MODEL,
            "provider": {
                "agency-swarm": {
                    "name": "Agency Swarm",
                    "options": {
                        "baseURL": f"http://{_HOST}:{port}",
                        "agency": agency_id,
                        "discoveryTimeoutMs": 2000,
                    },
                }
            },
        }
    )
    return env


def _agency_id(agency) -> str:
    name = getattr(agency, "name", None) or "agency"
    return str(name).replace(" ", "_")


def _start_server(agency) -> _Server:
    port = _port()
    app = run_fastapi(
        agencies=build_fastapi_agencies(agency),
        host=_HOST,
        port=port,
        server_url=f"http://{_HOST}:{port}",
        app_token_env="",
        return_app=True,
    )
    if app is None:
        raise RuntimeError("Failed to build the Agency Swarm FastAPI app for Agent Swarm CLI.")

    import uvicorn

    config = uvicorn.Config(app=app, host=_HOST, port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    error: list[BaseException] = []

    def target() -> None:
        try:
            server.run()
        except BaseException as exc:  # pragma: no cover - surfaced by waiter below
            error.append(exc)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    _wait_for_server(port, server, thread, error)
    return _Server(port=port, server=server, thread=thread)


def _wait_for_server(
    port: int,
    server: _UvicornServer,
    thread: threading.Thread,
    error: list[BaseException],
) -> None:
    deadline = time.time() + 5
    while time.time() < deadline:
        if error:
            raise RuntimeError("Agency Swarm FastAPI server failed to start.") from error[0]
        if getattr(server, "started", False) and _can_connect(port):
            return
        if not thread.is_alive():
            break
        time.sleep(0.05)
    raise RuntimeError("Timed out waiting for the Agency Swarm FastAPI server to start.")


def _can_connect(port: int) -> bool:
    with suppress(OSError):
        with socket.create_connection((_HOST, port), timeout=0.2):
            return True
    return False


def _port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((_HOST, 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


def _ensure_cli() -> Path:
    pkg = _package()
    root = _cache() / _CLI_VERSION / pkg.name
    path = root / pkg.binary
    if path.exists():
        _chmod(path)
        return path

    root.mkdir(parents=True, exist_ok=True)
    with _lock(root / ".lock"):
        if path.exists():
            _chmod(path)
            return path
        _install(pkg, root, path)
    return path


def _install(pkg: _Package, root: Path, path: Path) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="agentswarm-", dir=root))
    try:
        archive = tmp / "cli.tgz"
        meta = _metadata(pkg.name)
        _download(meta["dist"]["tarball"], archive)
        if meta["dist"].get("shasum") and _sha1(archive) != meta["dist"]["shasum"]:
            raise RuntimeError("Agent Swarm CLI download checksum mismatch.")
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(tmp, filter="data")
        source = tmp / "package" / "bin" / pkg.binary
        if not source.exists():
            raise RuntimeError("Agent Swarm CLI package is missing its executable.")
        part = root / f"{pkg.binary}.part"
        with suppress(FileNotFoundError):
            part.unlink()
        shutil.move(str(source), part)
        _chmod(part)
        os.replace(part, path)
    except Exception as exc:
        raise RuntimeError(
            "Agent Swarm CLI could not be installed automatically. Check your network and try again."
        ) from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _metadata(name: str) -> _Meta:
    response = requests.get(f"{_CLI_REGISTRY}/{name}/{_CLI_VERSION}", timeout=30)
    response.raise_for_status()
    data = response.json()
    dist = data.get("dist") if isinstance(data, dict) else None
    if not isinstance(dist, dict) or not isinstance(dist.get("tarball"), str):
        raise RuntimeError("Agent Swarm CLI package metadata is invalid.")
    return {
        "dist": {
            "tarball": dist["tarball"],
            "shasum": dist.get("shasum") if isinstance(dist.get("shasum"), str) else None,
        }
    }


def _download(url: str, path: Path) -> None:
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with path.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1 << 20):
                if chunk:
                    file.write(chunk)


def _sha1(path: Path) -> str:
    hash = hashlib.sha1()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            hash.update(chunk)
    return hash.hexdigest()


def _cache() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "agency-swarm" / "agentswarm-cli"
    if sys.platform == "win32":
        root = Path(os.environ["LOCALAPPDATA"]) if os.environ.get("LOCALAPPDATA") else Path.home() / "AppData/Local"
        return root / "Agency Swarm" / "agentswarm-cli"
    base = Path(os.environ["XDG_CACHE_HOME"]) if os.environ.get("XDG_CACHE_HOME") else Path.home() / ".cache"
    return base / "agency-swarm" / "agentswarm-cli"


def _package() -> _Package:
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        if machine in ("aarch64", "arm64"):
            return _Package("agent-swarm-cli-darwin-arm64", "agency")
        if machine in ("amd64", "x86_64"):
            return _Package("agent-swarm-cli-darwin-x64-baseline", "agency")
    if sys.platform == "win32":
        if machine in ("aarch64", "arm64"):
            return _Package("agent-swarm-cli-windows-arm64", "agency.exe")
        if machine in ("amd64", "x86_64"):
            return _Package("agent-swarm-cli-windows-x64-baseline", "agency.exe")
    if sys.platform.startswith("linux"):
        if machine in ("aarch64", "arm64"):
            name = "agent-swarm-cli-linux-arm64"
        elif machine in ("amd64", "x86_64"):
            name = "agent-swarm-cli-linux-x64-baseline"
        else:
            name = ""
        if name:
            if _musl():
                name += "-musl"
            return _Package(name, "agency")
    raise RuntimeError(f"Agent Swarm CLI is not available on {sys.platform}/{machine}.")


def _musl() -> bool:
    if Path("/etc/alpine-release").exists():
        return True
    with suppress(Exception):
        result = subprocess.run(["ldd", "--version"], capture_output=True, check=False, text=True)
        text = f"{result.stdout}{result.stderr}".lower()
        return "musl" in text
    return False


def _chmod(path: Path) -> None:
    if os.name != "nt":
        path.chmod(0o755)


@contextmanager
def _lock(path: Path):
    fd: int | None = None
    err: FileExistsError | None = None
    deadline = time.time() + _LOCK_WAIT
    while fd is None:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except FileExistsError as exc:
            err = exc
            if path.exists() and time.time() - path.stat().st_mtime > _LOCK_AGE:
                with suppress(FileNotFoundError):
                    path.unlink()
                continue
            if time.time() >= deadline:
                raise RuntimeError("Timed out waiting for Agent Swarm CLI install lock.") from err
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        with suppress(FileNotFoundError):
            path.unlink()

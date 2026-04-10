from __future__ import annotations

import os
import shlex
import socket
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from agency_swarm.integrations.openclaw import OpenClawRuntime
from tests.integration.fastapi._openclaw_test_support import _build_openclaw_config


def _reserve_free_port() -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])
    except PermissionError as exc:
        pytest.skip(f"loopback bind unavailable in this environment: {exc}")


def _write_fake_node_binary(tmp_path: Path) -> Path:
    script_path = tmp_path / "node"
    script_path.write_text(
        """#!/bin/sh
if [ "$1" = "--version" ]; then
  echo "v22.12.0"
  exit 0
fi
echo "unexpected invocation: $@" >&2
exit 1
""",
        encoding="utf-8",
    )
    script_path.chmod(0o755)
    return script_path


def _write_gateway_script(tmp_path: Path) -> Path:
    script_path = tmp_path / "fake_gateway.py"
    script_path.write_text(
        """
from __future__ import annotations

import argparse
import signal
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args, **_kwargs):
        return None

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--pid-file")
    args = parser.parse_args()
    if args.pid_file:
        with open(args.pid_file, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))

    if args.mode == "exit":
        print("fatal gateway error", flush=True)
        return 1

    if args.mode == "sleep":
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        while True:
            time.sleep(1)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    signal.signal(signal.SIGTERM, lambda *_: server.shutdown())
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    import os
    raise SystemExit(main())
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return script_path


def _build_gateway_command(script_path: Path, *, mode: str, port: int, pid_file: Path | None = None) -> str:
    command = [
        shlex.quote(sys.executable),
        shlex.quote(str(script_path)),
        "--mode",
        shlex.quote(mode),
        "--port",
        str(port),
    ]
    if pid_file is not None:
        command.extend(["--pid-file", shlex.quote(str(pid_file))])
    return " ".join(command)


def _process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def test_openclaw_runtime_start_and_stop_real_gateway_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    port = _reserve_free_port()
    script_path = _write_gateway_script(tmp_path)
    monkeypatch.setenv("OPENCLAW_NODE_BIN", str(_write_fake_node_binary(tmp_path)))
    config = replace(
        _build_openclaw_config(tmp_path),
        port=port,
        gateway_command=_build_gateway_command(script_path, mode="serve", port=port),
        startup_timeout_seconds=5.0,
    )
    runtime = OpenClawRuntime(config)

    runtime.start()

    assert runtime.is_running is True
    assert runtime.health()["running"] is True

    runtime.stop()

    assert runtime.is_running is False
    assert runtime._process is None
    assert runtime._log_handle is None


def test_openclaw_runtime_start_reports_early_exit_log_tail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    port = _reserve_free_port()
    script_path = _write_gateway_script(tmp_path)
    monkeypatch.setenv("OPENCLAW_NODE_BIN", str(_write_fake_node_binary(tmp_path)))
    runtime = OpenClawRuntime(
        replace(
            _build_openclaw_config(tmp_path),
            port=port,
            gateway_command=_build_gateway_command(script_path, mode="exit", port=port),
            startup_timeout_seconds=2.0,
        )
    )

    with pytest.raises(RuntimeError, match="OpenClaw exited early with code 1") as excinfo:
        runtime.start()

    assert "fatal gateway error" in str(excinfo.value)
    assert runtime._process is None
    assert runtime._log_handle is None


def test_openclaw_runtime_timeout_cleans_up_real_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    port = _reserve_free_port()
    script_path = _write_gateway_script(tmp_path)
    pid_file = tmp_path / "sleep.pid"
    monkeypatch.setenv("OPENCLAW_NODE_BIN", str(_write_fake_node_binary(tmp_path)))
    runtime = OpenClawRuntime(
        replace(
            _build_openclaw_config(tmp_path),
            port=port,
            gateway_command=_build_gateway_command(script_path, mode="sleep", port=port, pid_file=pid_file),
            startup_timeout_seconds=0.5,
        )
    )

    with pytest.raises(TimeoutError):
        runtime.start()

    pid = int(pid_file.read_text(encoding="utf-8"))
    deadline = time.time() + 2.0
    while time.time() < deadline and _process_is_alive(pid):
        time.sleep(0.05)

    assert _process_is_alive(pid) is False
    assert runtime._process is None
    assert runtime._log_handle is None

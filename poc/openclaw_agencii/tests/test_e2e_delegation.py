from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from openclaw_runtime import OpenClawRuntime


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(url: str, timeout_seconds: float = 240.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error = "no response"
    while time.time() < deadline:
        try:
            response = httpx.get(url, timeout=2.0)
            if response.status_code == 200:
                return
            last_error = f"status={response.status_code}"
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_error = str(exc)
        time.sleep(1.0)
    raise AssertionError(f"Timed out waiting for health endpoint {url}: {last_error}")


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


@pytest.mark.skipif(os.getenv("RUN_OPENCLAW_E2E") != "1", reason="Set RUN_OPENCLAW_E2E=1 to run live E2E test")
def test_openclaw_delegation_e2e(tmp_path: Path) -> None:
    if not shutil.which("openclaw") and not shutil.which("npx"):
        pytest.skip("OpenClaw runtime requires either `openclaw` or `npx` in PATH")

    openai_api_key, _ = OpenClawRuntime._resolve_openai_api_key()
    if not openai_api_key:
        pytest.skip("OPENAI_API_KEY is not available from repo .env or process environment")

    repo_root = Path(__file__).resolve().parents[3]
    app_port = _pick_free_port()
    openclaw_port = _pick_free_port()

    runtime_dir = tmp_path / "runtime"
    app_log_path = tmp_path / "app.log"
    openclaw_log_path = runtime_dir / "openclaw-gateway.log"

    env = os.environ.copy()
    env.update(
        {
            "PORT": str(app_port),
            "OPENCLAW_AUTOSTART": "true",
            "OPENCLAW_STARTUP_TIMEOUT_SECONDS": "240",
            "OPENCLAW_HOST": "127.0.0.1",
            "OPENCLAW_PORT": str(openclaw_port),
            "OPENCLAW_DATA_DIR": str(runtime_dir / "data"),
            "OPENCLAW_STATE_DIR": str(runtime_dir / "state"),
            "OPENCLAW_CONFIG_PATH": str(runtime_dir / "openclaw.json"),
            "OPENCLAW_LOG_PATH": str(openclaw_log_path),
            "OPENCLAW_REPO_ENV_PATH": str(repo_root / ".env"),
        }
    )
    if not shutil.which("openclaw"):
        env["OPENCLAW_GATEWAY_COMMAND"] = "npx -y openclaw@latest gateway --verbose"

    process: subprocess.Popen[bytes] | None = None
    try:
        with app_log_path.open("wb") as log_file:
            process = subprocess.Popen(
                [sys.executable, "poc/openclaw_agencii/main.py"],
                cwd=str(repo_root),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )

            _wait_for_health(f"http://127.0.0.1:{app_port}/healthz")

            response = httpx.post(
                f"http://127.0.0.1:{app_port}/openclaw-poc/get_response",
                json={
                    "message": (
                        "You are Coordinator. Delegate this task to OpenClawSpecialist and return the specialist "
                        "answer only. Task: reply exactly with DELEGATION_WORKED."
                    ),
                    "recipient_agent": "Coordinator",
                },
                timeout=300.0,
            )

            assert response.status_code == 200, response.text
            payload = response.json()
            assert "DELEGATION_WORKED" in str(payload.get("response"))

            found_delegation_marker = False
            for _ in range(30):
                if openclaw_log_path.exists():
                    log_text = openclaw_log_path.read_text(encoding="utf-8", errors="replace")
                    if "sessions_spawn" in log_text and "subagent:" in log_text:
                        found_delegation_marker = True
                        break
                time.sleep(1.0)
            assert found_delegation_marker, "OpenClaw delegation markers were not found in gateway logs"
    finally:
        if process is not None:
            _terminate_process(process)

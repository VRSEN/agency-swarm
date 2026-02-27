from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpenClawRuntimeConfig:
    """Runtime settings for launching OpenClaw in the PoC container."""

    autostart: bool
    host: str
    port: int
    gateway_token: str
    data_dir: Path
    state_dir: Path
    config_path: Path
    log_path: Path
    startup_timeout_seconds: float
    default_model: str
    gateway_command: str | None

    @classmethod
    def from_env(cls) -> OpenClawRuntimeConfig:
        data_dir = Path(os.getenv("OPENCLAW_DATA_DIR", "/mnt/openclaw")).expanduser().resolve()
        state_dir = Path(os.getenv("OPENCLAW_STATE_DIR", str(data_dir / "state"))).expanduser().resolve()
        config_path = Path(os.getenv("OPENCLAW_CONFIG_PATH", str(data_dir / "openclaw.json"))).expanduser().resolve()
        log_path = Path(os.getenv("OPENCLAW_LOG_PATH", str(data_dir / "openclaw-gateway.log"))).expanduser().resolve()

        return cls(
            autostart=os.getenv("OPENCLAW_AUTOSTART", "true").lower() in {"1", "true", "yes", "on"},
            host=os.getenv("OPENCLAW_HOST", "127.0.0.1"),
            port=int(os.getenv("OPENCLAW_PORT", "18789")),
            gateway_token=os.getenv("OPENCLAW_GATEWAY_TOKEN", "openclaw-local-token"),
            data_dir=data_dir,
            state_dir=state_dir,
            config_path=config_path,
            log_path=log_path,
            startup_timeout_seconds=float(os.getenv("OPENCLAW_STARTUP_TIMEOUT_SECONDS", "60")),
            default_model=os.getenv("OPENCLAW_DEFAULT_MODEL", "openai/gpt-4o-mini"),
            gateway_command=os.getenv("OPENCLAW_GATEWAY_COMMAND"),
        )


class OpenClawRuntime:
    """Manages an OpenClaw gateway subprocess for local PoC runs."""

    def __init__(self, config: OpenClawRuntimeConfig):
        self.config = config
        self._process: subprocess.Popen[bytes] | None = None
        self._log_handle: Any | None = None

    @property
    def upstream_base_url(self) -> str:
        return f"http://{self.config.host}:{self.config.port}"

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @staticmethod
    def _candidate_env_paths() -> list[Path]:
        candidates: list[Path] = []
        explicit = os.getenv("OPENCLAW_REPO_ENV_PATH")
        if explicit:
            candidates.append(Path(explicit).expanduser())

        repo_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if repo_root.returncode == 0 and repo_root.stdout.strip():
            candidates.append(Path(repo_root.stdout.strip()) / ".env")

        worktrees = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
        if worktrees.returncode == 0:
            for line in worktrees.stdout.splitlines():
                if line.startswith("worktree "):
                    worktree_path = line.split(" ", 1)[1].strip()
                    if worktree_path:
                        candidates.append(Path(worktree_path) / ".env")

        unique_paths: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = str(candidate.resolve())
            if normalized in seen:
                continue
            seen.add(normalized)
            unique_paths.append(Path(normalized))
        return unique_paths

    @classmethod
    def _find_openai_api_key_from_env_file(cls) -> tuple[str | None, Path | None]:
        for env_path in cls._candidate_env_paths():
            if not env_path.exists():
                continue
            env_values = dotenv_values(env_path)
            openai_api_key = env_values.get("OPENAI_API_KEY")
            if isinstance(openai_api_key, str):
                normalized = openai_api_key.strip()
                if normalized:
                    return normalized, env_path
        return None, None

    @classmethod
    def _resolve_openai_api_key(cls) -> tuple[str | None, Path | None]:
        openai_api_key, source_path = cls._find_openai_api_key_from_env_file()
        if openai_api_key:
            return openai_api_key, source_path

        env_value = os.getenv("OPENAI_API_KEY")
        if env_value and env_value.strip():
            return env_value.strip(), None
        return None, None

    @staticmethod
    def _normalize_model_config(model: Any) -> dict[str, Any] | None:
        if isinstance(model, str):
            normalized = model.strip()
            if normalized:
                return {"primary": normalized}
            return None

        if not isinstance(model, dict):
            return None

        normalized: dict[str, Any] = {}
        primary = model.get("primary")
        if isinstance(primary, str) and primary.strip():
            normalized["primary"] = primary.strip()

        fallbacks = model.get("fallbacks")
        if isinstance(fallbacks, list):
            normalized_fallbacks = [item.strip() for item in fallbacks if isinstance(item, str) and item.strip()]
            if normalized_fallbacks:
                normalized["fallbacks"] = normalized_fallbacks

        if normalized:
            return normalized
        return None

    def ensure_layout(self) -> None:
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        self.config.state_dir.mkdir(parents=True, exist_ok=True)
        self.config.log_path.parent.mkdir(parents=True, exist_ok=True)

        if self.config.config_path.exists():
            try:
                current = json.loads(self.config.config_path.read_text(encoding="utf-8"))
            except Exception:
                current = {}
        else:
            current = {}

        if not isinstance(current, dict):
            current = {}

        legacy_agent = current.pop("agent", None)
        legacy_model = legacy_agent.get("model") if isinstance(legacy_agent, dict) else None

        gateway = current.setdefault("gateway", {})
        if not isinstance(gateway, dict):
            gateway = {}
            current["gateway"] = gateway
        gateway.setdefault("mode", "local")
        gateway.setdefault("bind", "loopback")
        gateway.setdefault("port", self.config.port)
        auth = gateway.setdefault("auth", {})
        if not isinstance(auth, dict):
            auth = {}
            gateway["auth"] = auth
        auth.setdefault("mode", "token")
        auth.setdefault("token", self.config.gateway_token)

        http_cfg = gateway.setdefault("http", {})
        if not isinstance(http_cfg, dict):
            http_cfg = {}
            gateway["http"] = http_cfg
        endpoints = http_cfg.setdefault("endpoints", {})
        if not isinstance(endpoints, dict):
            endpoints = {}
            http_cfg["endpoints"] = endpoints
        responses = endpoints.setdefault("responses", {})
        if not isinstance(responses, dict):
            responses = {}
            endpoints["responses"] = responses
        responses["enabled"] = True

        agents = current.setdefault("agents", {})
        if not isinstance(agents, dict):
            agents = {}
            current["agents"] = agents
        defaults = agents.setdefault("defaults", {})
        if not isinstance(defaults, dict):
            defaults = {}
            agents["defaults"] = defaults
        if "model" not in defaults:
            defaults["model"] = self._normalize_model_config(legacy_model) or self._normalize_model_config(
                self.config.default_model
            )

        self.config.config_path.write_text(json.dumps(current, indent=2), encoding="utf-8")

    def _resolve_gateway_command(self) -> list[str]:
        if self.config.gateway_command:
            cmd = shlex.split(self.config.gateway_command)
        elif shutil.which("openclaw"):
            cmd = ["openclaw", "gateway"]
        elif shutil.which("npx"):
            cmd = ["npx", "-y", "openclaw@latest", "gateway"]
        else:
            raise RuntimeError("OpenClaw runtime unavailable: install `openclaw` or provide OPENCLAW_GATEWAY_COMMAND")

        if "--port" not in cmd:
            cmd.extend(["--port", str(self.config.port)])

        return cmd

    def _is_port_open(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            try:
                sock.connect((self.config.host, self.config.port))
            except OSError:
                return False
        return True

    def start(self) -> None:
        if self.is_running:
            logger.info("OpenClaw runtime already running")
            return

        self.ensure_layout()
        cmd = self._resolve_gateway_command()
        logger.info("Starting OpenClaw runtime: %s", " ".join(cmd))

        env = os.environ.copy()
        env["OPENCLAW_HOME"] = str(self.config.data_dir)
        env["OPENCLAW_STATE_DIR"] = str(self.config.state_dir)
        env["OPENCLAW_CONFIG_PATH"] = str(self.config.config_path)
        env["OPENCLAW_GATEWAY_TOKEN"] = self.config.gateway_token
        openai_api_key, source_path = self._resolve_openai_api_key()
        if openai_api_key:
            env["OPENAI_API_KEY"] = openai_api_key
            if source_path is not None:
                logger.info("Loaded OPENAI_API_KEY from %s", source_path)
        else:
            logger.warning("OPENAI_API_KEY not found in repo .env or process environment")

        self._log_handle = self.config.log_path.open("ab", buffering=0)
        self._process = subprocess.Popen(
            cmd,
            cwd=str(self.config.data_dir),
            env=env,
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        deadline = time.time() + self.config.startup_timeout_seconds
        while time.time() < deadline:
            if self._process.poll() is not None:
                raise RuntimeError(
                    f"OpenClaw exited early with code {self._process.returncode}. Check log: {self.config.log_path}"
                )
            if self._is_port_open():
                logger.info("OpenClaw runtime listening on %s", self.upstream_base_url)
                return
            time.sleep(0.4)

        raise TimeoutError(
            f"Timed out waiting for OpenClaw to start at {self.upstream_base_url}. Log: {self.config.log_path}"
        )

    def stop(self) -> None:
        if self._process is None:
            return

        proc = self._process
        self._process = None

        try:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except Exception:
                    proc.terminate()
                proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            logger.warning("OpenClaw runtime did not stop in time; force killing")
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                proc.kill()
            proc.wait(timeout=5)
        finally:
            if self._log_handle is not None:
                self._log_handle.close()
                self._log_handle = None

    def health(self) -> dict[str, Any]:
        return {
            "running": self.is_running,
            "upstream_base_url": self.upstream_base_url,
            "config_path": str(self.config.config_path),
            "log_path": str(self.config.log_path),
        }

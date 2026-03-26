from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import time
import weakref
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from agents import OpenAIResponsesModel
from dotenv import dotenv_values
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from . import openclaw_model
from .openclaw_model import DEFAULT_OPENCLAW_MODEL, DEFAULT_OPENCLAW_PROXY_API_PATH

logger = logging.getLogger(__name__)

_OPENRESPONSES_ALLOWED_KEYS: tuple[str, ...] = (
    "model",
    "input",
    "instructions",
    "tools",
    "tool_choice",
    "stream",
    "max_output_tokens",
    "max_tool_calls",
    "user",
    "temperature",
    "top_p",
    "metadata",
    "store",
    "previous_response_id",
    "reasoning",
    "truncation",
)
_ALLOWED_TOOL_CHOICE_VALUES = {"auto", "none", "required"}
_PROVIDER_ENV_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")
_RESPONSE_HEADER_BLOCKLIST = {"content-length", "transfer-encoding", "connection"}
_RESPONSE_HEADER_BLOCKLIST_DECODED = _RESPONSE_HEADER_BLOCKLIST | {"content-encoding"}
_MIN_NODE_VERSION = (22, 12, 0)
_DEFAULT_NODE_CANDIDATES = ("/opt/homebrew/bin/node", "/usr/local/bin/node")


def _extract_port_from_gateway_command(command: list[str]) -> int | None:
    for idx, arg in enumerate(command):
        value: str | None = None
        if arg == "--port":
            if idx + 1 >= len(command):
                return None
            value = command[idx + 1]
        elif arg.startswith("--port="):
            value = arg.split("=", 1)[1]

        if value is None:
            continue

        try:
            port = int(value)
        except ValueError:
            return None
        return port if 1 <= port <= 65535 else None
    return None


def _read_log_tail(log_path: Path, max_bytes: int = 4096) -> str:
    try:
        with log_path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(size - max_bytes, 0))
            return handle.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return ""


def _read_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _default_gateway_token() -> str:
    app_token = os.getenv("APP_TOKEN", "").strip()
    if app_token:
        return app_token
    return "openclaw-local-token"


def _workspace_suffix(profile: str | None) -> str:
    if not isinstance(profile, str):
        return ""
    normalized = profile.strip()
    if not normalized or normalized.lower() == "default":
        return ""
    return f"-{normalized}"


def _default_agent_has_explicit_workspace(agents: dict[str, Any]) -> bool:
    entries = agents.get("list")
    if not isinstance(entries, list):
        return False
    normalized_entries = [entry for entry in entries if isinstance(entry, dict)]
    if not normalized_entries:
        return False
    default_entry = next((entry for entry in normalized_entries if entry.get("default")), normalized_entries[0])
    workspace = default_entry.get("workspace")
    return isinstance(workspace, str) and bool(workspace.strip())


def _parse_node_semver(raw: str) -> tuple[int, int, int] | None:
    match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", raw.strip())
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _read_node_version(binary_path: str) -> tuple[int, int, int] | None:
    try:
        completed = subprocess.run(
            [binary_path, "--version"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    version_text = completed.stdout.strip() or completed.stderr.strip()
    return _parse_node_semver(version_text)


def _select_compatible_node_binary() -> tuple[str | None, tuple[int, int, int] | None]:
    candidates: list[str] = []
    explicit = os.getenv("OPENCLAW_NODE_BIN")
    if explicit:
        candidates.append(explicit)
    path_node = shutil.which("node")
    if path_node:
        candidates.append(path_node)
    candidates.extend(_DEFAULT_NODE_CANDIDATES)

    seen: set[str] = set()
    best_detected: tuple[int, int, int] | None = None
    for candidate in candidates:
        resolved = str(Path(candidate).expanduser())
        if resolved in seen:
            continue
        seen.add(resolved)
        version = _read_node_version(resolved)
        if version is None:
            continue
        if best_detected is None or version > best_detected:
            best_detected = version
        if version >= _MIN_NODE_VERSION:
            return resolved, version
    return None, best_detected


@dataclass(frozen=True)
class OpenClawIntegrationConfig:
    """Runtime and proxy settings for OpenClaw integration."""

    autostart: bool
    host: str
    port: int
    gateway_token: str
    home_dir: Path
    state_dir: Path
    config_path: Path
    log_path: Path
    startup_timeout_seconds: float
    proxy_timeout_seconds: float
    default_model: str
    provider_model: str
    gateway_command: str | None
    profile: str | None = None
    tool_mode: str = "full"

    @property
    def upstream_base_url(self) -> str:
        host = self.host
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"http://{host}:{self.port}"

    @property
    def workspace_dir(self) -> Path:
        return self.home_dir / f"workspace{_workspace_suffix(self.profile or os.getenv('OPENCLAW_PROFILE'))}"

    @property
    def legacy_workspace_dir(self) -> Path:
        return (
            self.home_dir / ".openclaw" / f"workspace{_workspace_suffix(self.profile or os.getenv('OPENCLAW_PROFILE'))}"
        )

    @classmethod
    def from_env(cls) -> OpenClawIntegrationConfig:
        home_dir = Path(os.getenv("OPENCLAW_HOME", "/mnt/openclaw")).expanduser().resolve()
        state_dir = Path(os.getenv("OPENCLAW_STATE_DIR", str(home_dir / "state"))).expanduser().resolve()
        config_path = Path(os.getenv("OPENCLAW_CONFIG_PATH", str(home_dir / "openclaw.json"))).expanduser().resolve()
        log_path = (
            Path(os.getenv("OPENCLAW_LOG_PATH", str(home_dir / "logs" / "openclaw-gateway.log"))).expanduser().resolve()
        )
        configured_port = int(os.getenv("OPENCLAW_PORT", "18789"))
        gateway_command = os.getenv("OPENCLAW_GATEWAY_COMMAND")
        resolved_port = configured_port
        if gateway_command:
            try:
                command_parts = shlex.split(gateway_command)
            except ValueError:
                command_parts = []
            command_port = _extract_port_from_gateway_command(command_parts)
            if command_port is not None:
                resolved_port = command_port

        return cls(
            autostart=_read_bool_env("OPENCLAW_AUTOSTART", default=True),
            host=os.getenv("OPENCLAW_HOST", "127.0.0.1"),
            port=resolved_port,
            gateway_token=os.getenv("OPENCLAW_GATEWAY_TOKEN") or _default_gateway_token(),
            home_dir=home_dir,
            state_dir=state_dir,
            config_path=config_path,
            log_path=log_path,
            startup_timeout_seconds=float(os.getenv("OPENCLAW_STARTUP_TIMEOUT_SECONDS", "60")),
            proxy_timeout_seconds=float(os.getenv("OPENCLAW_PROXY_TIMEOUT_SECONDS", "120")),
            default_model=os.getenv("OPENCLAW_DEFAULT_MODEL", DEFAULT_OPENCLAW_MODEL),
            provider_model=os.getenv("OPENCLAW_PROVIDER_MODEL", "openai/gpt-5.4"),
            gateway_command=gateway_command,
            profile=os.getenv("OPENCLAW_PROFILE"),
            tool_mode=_read_openclaw_tool_mode_env(),
        )


class OpenClawRuntime:
    """Manage an OpenClaw gateway process for a FastAPI app."""

    def __init__(self, config: OpenClawIntegrationConfig):
        self.config = config
        self._process: subprocess.Popen[bytes] | None = None
        self._log_handle: Any | None = None

    @property
    def upstream_base_url(self) -> str:
        return self.config.upstream_base_url

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _resolve_dotenv_path(self) -> Path | None:
        explicit = os.getenv("OPENCLAW_DOTENV_PATH")
        if explicit:
            path = Path(explicit).expanduser().resolve()
            return path if path.exists() else None

        cwd = Path.cwd().resolve()
        for candidate_dir in [cwd, *cwd.parents]:
            candidate = candidate_dir / ".env"
            if candidate.exists():
                return candidate
        return None

    def _merge_provider_keys_from_dotenv(self, env: dict[str, str]) -> None:
        dotenv_path = self._resolve_dotenv_path()
        if dotenv_path is None:
            return

        values = dotenv_values(dotenv_path)
        loaded_keys: list[str] = []
        for key, value in values.items():
            if not isinstance(key, str) or key not in _PROVIDER_ENV_KEYS:
                continue
            if not isinstance(value, str) or not value.strip():
                continue
            if env.get(key):
                continue
            env[key] = value.strip()
            loaded_keys.append(key)

        if loaded_keys:
            logger.info("Loaded provider keys from %s: %s", dotenv_path, ", ".join(sorted(loaded_keys)))

    @staticmethod
    def _normalize_model_config(model: Any) -> dict[str, Any] | None:
        if isinstance(model, str):
            model_name = model.strip()
            return {"primary": model_name} if model_name else None

        if not isinstance(model, dict):
            return None

        normalized: dict[str, Any] = {}
        primary = model.get("primary")
        if isinstance(primary, str) and primary.strip():
            normalized["primary"] = primary.strip()

        fallbacks = model.get("fallbacks")
        if isinstance(fallbacks, list):
            normalized_fallbacks = [value.strip() for value in fallbacks if isinstance(value, str) and value.strip()]
            if normalized_fallbacks:
                normalized["fallbacks"] = normalized_fallbacks

        return normalized or None

    def ensure_layout(self) -> None:
        self.config.home_dir.mkdir(parents=True, exist_ok=True)
        self.config.state_dir.mkdir(parents=True, exist_ok=True)
        self.config.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.log_path.parent.mkdir(parents=True, exist_ok=True)

        if self.config.config_path.exists():
            try:
                current = json.loads(self.config.config_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                current = {}
        else:
            current = {}

        if not isinstance(current, dict):
            current = {}

        gateway = current.setdefault("gateway", {})
        if not isinstance(gateway, dict):
            gateway = {}
            current["gateway"] = gateway
        gateway.setdefault("mode", "local")
        gateway.setdefault("bind", "loopback")
        gateway["port"] = self.config.port

        auth = gateway.setdefault("auth", {})
        if not isinstance(auth, dict):
            auth = {}
            gateway["auth"] = auth
        auth["mode"] = "token"
        auth["token"] = self.config.gateway_token

        http_config = gateway.setdefault("http", {})
        if not isinstance(http_config, dict):
            http_config = {}
            gateway["http"] = http_config
        endpoints = http_config.setdefault("endpoints", {})
        if not isinstance(endpoints, dict):
            endpoints = {}
            http_config["endpoints"] = endpoints
        responses = endpoints.setdefault("responses", {})
        if not isinstance(responses, dict):
            responses = {}
            endpoints["responses"] = responses
        responses["enabled"] = True

        backup_to_remove = _apply_tool_mode_config(current, self.config.tool_mode, self.config.config_path)

        agents = current.setdefault("agents", {})
        if not isinstance(agents, dict):
            agents = {}
            current["agents"] = agents
        defaults = agents.setdefault("defaults", {})
        if not isinstance(defaults, dict):
            defaults = {}
            agents["defaults"] = defaults
        if "model" not in defaults:
            defaults["model"] = self._normalize_model_config(self.config.provider_model)
        if not _default_agent_has_explicit_workspace(agents):
            self._ensure_default_workspace(defaults)

        config_payload = json.dumps(current, indent=2)
        fd = os.open(self.config.config_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as config_file:
            config_file.write(config_payload)
        try:
            self.config.config_path.chmod(0o600)
        except OSError:
            logger.debug("Unable to set restrictive permissions on OpenClaw config path", exc_info=True)
        if backup_to_remove is not None:
            _remove_tool_mode_backup(backup_to_remove)
        if self.config.tool_mode == "worker":
            _record_worker_tool_mode_state(
                self.config.config_path, _tool_mode_backup_path(self.config.config_path), current
            )

    def _ensure_default_workspace(self, defaults: dict[str, Any]) -> None:
        workspace = defaults.get("workspace")
        if isinstance(workspace, str) and workspace.strip():
            return

        legacy_workspace_dir = self.config.legacy_workspace_dir
        workspace_dir = self.config.workspace_dir

        if legacy_workspace_dir.exists():
            if not workspace_dir.exists():
                workspace_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(legacy_workspace_dir), str(workspace_dir))
            elif workspace_dir.is_dir() and not any(workspace_dir.iterdir()):
                for child in legacy_workspace_dir.iterdir():
                    shutil.move(str(child), str(workspace_dir / child.name))
                try:
                    legacy_workspace_dir.rmdir()
                except OSError:
                    logger.debug("Unable to remove migrated OpenClaw legacy workspace dir", exc_info=True)
            elif legacy_workspace_dir.is_dir() and any(legacy_workspace_dir.iterdir()):
                defaults["workspace"] = str(legacy_workspace_dir)
                return

        if workspace_dir.exists() and not workspace_dir.is_dir():
            raise RuntimeError(
                f"OpenClaw workspace path collision at {workspace_dir}. "
                "Remove the file or set agents.defaults.workspace explicitly."
            )
        workspace_dir.mkdir(parents=True, exist_ok=True)
        defaults["workspace"] = str(workspace_dir)

    def _resolve_gateway_command(self) -> list[str]:
        if self.config.gateway_command:
            try:
                command = shlex.split(self.config.gateway_command)
            except ValueError as exc:
                raise RuntimeError(
                    "Invalid OPENCLAW_GATEWAY_COMMAND value. Please verify shell quoting and command format."
                ) from exc
        elif shutil.which("openclaw"):
            command = ["openclaw", "gateway"]
        else:
            raise RuntimeError(
                "OpenClaw runtime unavailable. Install a pinned `openclaw` binary "
                "or set OPENCLAW_GATEWAY_COMMAND to a deterministic command."
            )

        has_port_flag = any(arg == "--port" or arg.startswith("--port=") for arg in command)
        detected_port = _extract_port_from_gateway_command(command)
        if has_port_flag and detected_port is None:
            raise RuntimeError(
                "Invalid OPENCLAW_GATEWAY_COMMAND --port value. Use --port <int> or --port=<int> with 1-65535."
            )
        if has_port_flag and detected_port is not None and detected_port != self.config.port:
            raise RuntimeError(
                "OPENCLAW_GATEWAY_COMMAND port does not match configured OPENCLAW_PORT. "
                "Use matching values or omit --port from OPENCLAW_GATEWAY_COMMAND."
            )
        if not has_port_flag:
            command.extend(["--port", str(self.config.port)])
        return command

    def _is_port_open(self) -> bool:
        return _is_upstream_port_open(self.config, timeout=0.5)

    def start(self) -> None:
        if self.is_running:
            return

        if self._is_port_open():
            raise RuntimeError(
                f"OpenClaw runtime port {self.config.port} is already in use at {self.upstream_base_url}. "
                "Set OPENCLAW_AUTOSTART=false to use an externally managed gateway."
            )

        self.ensure_layout()
        command = self._resolve_gateway_command()

        env = os.environ.copy()
        env["OPENCLAW_HOME"] = str(self.config.home_dir)
        env["OPENCLAW_STATE_DIR"] = str(self.config.state_dir)
        env["OPENCLAW_CONFIG_PATH"] = str(self.config.config_path)
        env["OPENCLAW_LOG_PATH"] = str(self.config.log_path)
        env["OPENCLAW_GATEWAY_TOKEN"] = self.config.gateway_token

        node_binary, detected_node_version = _select_compatible_node_binary()
        if node_binary is None:
            detected = "."
            if detected_node_version is not None:
                detected = (
                    f"; detected highest available node "
                    f"{detected_node_version[0]}.{detected_node_version[1]}.{detected_node_version[2]}."
                )
            raise RuntimeError(
                "OpenClaw requires Node >= "
                f"{_MIN_NODE_VERSION[0]}.{_MIN_NODE_VERSION[1]}.{_MIN_NODE_VERSION[2]}{detected} "
                "Install a compatible Node version or set OPENCLAW_NODE_BIN to a compatible binary path."
            )
        node_bin_dir = str(Path(node_binary).resolve().parent)
        path_parts = env.get("PATH", "").split(os.pathsep) if env.get("PATH") else []
        if not path_parts or path_parts[0] != node_bin_dir:
            env["PATH"] = os.pathsep.join([node_bin_dir, *path_parts]) if path_parts else node_bin_dir

        self._merge_provider_keys_from_dotenv(env)

        missing_provider_keys = [key for key in _PROVIDER_ENV_KEYS if not env.get(key)]
        if len(missing_provider_keys) == len(_PROVIDER_ENV_KEYS):
            logger.warning("No provider API keys found in env (checked: %s)", ", ".join(_PROVIDER_ENV_KEYS))

        self._log_handle = self.config.log_path.open("ab", buffering=0)
        try:
            self._process = subprocess.Popen(
                command,
                cwd=str(self.config.home_dir),
                env=env,
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except Exception:
            if self._log_handle is not None:
                self._log_handle.close()
                self._log_handle = None
            self._process = None
            raise

        try:
            deadline = time.time() + self.config.startup_timeout_seconds
            while time.time() < deadline:
                if self._process.poll() is not None:
                    log_tail = _read_log_tail(self.config.log_path)
                    tail_message = f" Last gateway log output:\n{log_tail}" if log_tail else ""
                    raise RuntimeError(
                        f"OpenClaw exited early with code {self._process.returncode}. "
                        f"Check logs at {self.config.log_path}.{tail_message}"
                    )
                if self._is_port_open():
                    logger.info("OpenClaw runtime listening at %s", self.upstream_base_url)
                    return
                time.sleep(0.4)

            raise TimeoutError(f"Timed out waiting for OpenClaw at {self.upstream_base_url}")
        except Exception:
            self._cleanup_after_failed_start()
            raise

    def _cleanup_after_failed_start(self) -> None:
        process = self._process
        self._process = None
        try:
            if process is not None and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except Exception:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except Exception:
                        process.kill()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logger.warning("OpenClaw process did not stop during failed-start cleanup")
        except Exception:
            logger.warning("Unexpected error during failed-start cleanup", exc_info=True)
        finally:
            if self._log_handle is not None:
                try:
                    self._log_handle.close()
                except Exception:
                    logger.warning("OpenClaw log handle cleanup failed", exc_info=True)
                finally:
                    self._log_handle = None

    def stop(self) -> None:
        if self._process is None:
            return

        process = self._process
        self._process = None
        try:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except Exception:
                    process.terminate()
                process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            logger.warning("OpenClaw did not stop after SIGTERM; forcing kill")
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except Exception:
                process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("OpenClaw process did not stop after SIGKILL")
        except Exception:
            logger.warning("Unexpected error while stopping OpenClaw runtime", exc_info=True)
        finally:
            if self._log_handle is not None:
                try:
                    self._log_handle.close()
                except Exception:
                    logger.warning("OpenClaw log handle close failed during stop", exc_info=True)
                finally:
                    self._log_handle = None

    def health(self) -> dict[str, Any]:
        return {
            "running": self.is_running,
            "upstream_base_url": self.upstream_base_url,
            "home_dir": str(self.config.home_dir),
            "state_dir": str(self.config.state_dir),
            "config_path": str(self.config.config_path),
            "log_path": str(self.config.log_path),
        }


def _normalize_content_part(part: dict[str, Any]) -> dict[str, Any]:
    if "type" in part:
        return dict(part)
    if "text" in part and isinstance(part["text"], str):
        return {"type": "input_text", "text": part["text"]}
    return dict(part)


def _normalize_message_item(item: dict[str, Any]) -> dict[str, Any]:
    role = item.get("role")
    if not isinstance(role, str) or not role:
        raise ValueError("input message role must be a non-empty string")

    content = item.get("content")
    normalized: dict[str, Any] = {"type": "message", "role": role}
    if isinstance(content, str):
        normalized["content"] = content
        return normalized
    if isinstance(content, list):
        normalized["content"] = [_normalize_content_part(part) if isinstance(part, dict) else part for part in content]
        return normalized
    raise ValueError("input message content must be a string or list")


def _normalize_input_items(input_items: list[Any]) -> list[Any]:
    normalized_items: list[Any] = []
    for item in input_items:
        if not isinstance(item, dict):
            raise ValueError("input list items must be JSON objects")
        if "type" not in item and "role" in item and "content" in item:
            normalized_items.append(_normalize_message_item(item))
            continue
        if item.get("type") == "message":
            normalized_items.append(_normalize_message_item(item))
            continue
        normalized_items.append(dict(item))
    return normalized_items


def _normalize_tools(tools: Any) -> list[dict[str, Any]]:
    if tools is None:
        return []
    if not isinstance(tools, list):
        raise ValueError("tools must be a list")

    normalized_tools: list[dict[str, Any]] = []
    for index, tool in enumerate(tools):
        if not isinstance(tool, dict):
            raise ValueError(f"tools[{index}] must be an object")

        raw_tool_type = tool.get("type")
        if raw_tool_type != "function":
            raise ValueError(
                f"tools[{index}].type '{raw_tool_type}' is not supported by OpenClaw; "
                "only 'function' tools are supported"
            )

        function_payload = tool.get("function")
        function_name: str | None = None
        function_description: str | None = None
        function_parameters: dict[str, Any] | None = None
        function_strict: bool | None = None

        if isinstance(function_payload, dict):
            raw_name = function_payload.get("name")
            if isinstance(raw_name, str) and raw_name:
                function_name = raw_name

            raw_description = function_payload.get("description")
            if isinstance(raw_description, str) and raw_description:
                function_description = raw_description

            raw_parameters = function_payload.get("parameters")
            if isinstance(raw_parameters, dict):
                function_parameters = raw_parameters

            raw_strict = function_payload.get("strict")
            if isinstance(raw_strict, bool):
                function_strict = raw_strict

        if function_name is None:
            raw_name = tool.get("name")
            if isinstance(raw_name, str) and raw_name:
                function_name = raw_name

        if function_description is None:
            raw_description = tool.get("description")
            if isinstance(raw_description, str) and raw_description:
                function_description = raw_description

        if function_parameters is None:
            raw_parameters = tool.get("parameters")
            if isinstance(raw_parameters, dict):
                function_parameters = raw_parameters

        if function_strict is None:
            raw_strict = tool.get("strict")
            if isinstance(raw_strict, bool):
                function_strict = raw_strict

        if function_name is None:
            raise ValueError(f"tools[{index}] function name is required")

        normalized_function: dict[str, Any] = {"name": function_name}
        if function_description is not None:
            normalized_function["description"] = function_description
        if function_parameters is not None:
            normalized_function["parameters"] = function_parameters
        if function_strict is not None:
            normalized_function["strict"] = function_strict
        normalized_tools.append({"type": "function", "function": normalized_function})

    return normalized_tools


def _normalize_tool_choice(tool_choice: Any) -> str | dict[str, Any] | None:
    if tool_choice is None:
        return None

    if isinstance(tool_choice, str):
        return tool_choice if tool_choice in _ALLOWED_TOOL_CHOICE_VALUES else None

    if not isinstance(tool_choice, dict) or tool_choice.get("type") != "function":
        return None

    function_name: str | None = None
    function_payload = tool_choice.get("function")
    if isinstance(function_payload, dict):
        raw_name = function_payload.get("name")
        if isinstance(raw_name, str) and raw_name:
            function_name = raw_name
    if function_name is None:
        raw_name = tool_choice.get("name")
        if isinstance(raw_name, str) and raw_name:
            function_name = raw_name
    if function_name is None:
        return None

    return {"type": "function", "function": {"name": function_name}}


def _normalize_metadata(metadata: Any) -> dict[str, str] | None:
    if metadata is None:
        return None
    if not isinstance(metadata, dict):
        return None

    normalized: dict[str, str] = {}
    for key, value in metadata.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, str):
            normalized[key] = value
            continue
        try:
            normalized[key] = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"metadata['{key}'] must be JSON-serializable") from exc
    return normalized


def normalize_openclaw_responses_request(raw_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize Open Responses requests to OpenClaw-compatible shape."""
    payload = dict(raw_payload)

    model = payload.get("model")
    if not isinstance(model, str) or not model:
        raise ValueError("model is required and must be a non-empty string")
    if "input" not in payload:
        raise ValueError("input is required")

    input_payload = payload["input"]
    if isinstance(input_payload, str):
        normalized_input: str | list[Any] = input_payload
    elif isinstance(input_payload, list):
        normalized_input = _normalize_input_items(input_payload)
    else:
        raise ValueError("input must be a string or list")

    normalized: dict[str, Any] = {
        "model": model,
        "input": normalized_input,
    }

    for key in _OPENRESPONSES_ALLOWED_KEYS:
        if key in {"model", "input", "tools", "tool_choice", "metadata"}:
            continue
        if key in payload:
            normalized[key] = payload[key]

    if "tools" in payload:
        normalized_tools = _normalize_tools(payload.get("tools"))
        if normalized_tools:
            normalized["tools"] = normalized_tools

    if "tool_choice" in payload:
        normalized_tool_choice = _normalize_tool_choice(payload.get("tool_choice"))
        if normalized_tool_choice is not None:
            normalized["tool_choice"] = normalized_tool_choice

    if "metadata" in payload:
        normalized_metadata = _normalize_metadata(payload.get("metadata"))
        if normalized_metadata is not None:
            normalized["metadata"] = normalized_metadata

    return normalized


def _make_upstream_headers(token: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _passthrough_response_headers(upstream: httpx.Response, *, decoded_body: bool = False) -> dict[str, str]:
    blocked = _RESPONSE_HEADER_BLOCKLIST_DECODED if decoded_body else _RESPONSE_HEADER_BLOCKLIST
    return {key: value for key, value in upstream.headers.items() if key.lower() not in blocked}


def _forward_response_passthrough(upstream: httpx.Response) -> Response:
    headers = _passthrough_response_headers(upstream, decoded_body=True)
    content_type = headers.pop("content-type", "application/json")
    return Response(
        content=upstream.content, status_code=upstream.status_code, media_type=content_type, headers=headers
    )


def _read_openclaw_tool_mode_env() -> str:
    raw_value = os.getenv("OPENCLAW_TOOL_MODE", "full").strip().lower()
    if raw_value in {"", "full", "assistant"}:
        return "full"
    if raw_value == "worker":
        return raw_value
    raise RuntimeError("OPENCLAW_TOOL_MODE must be 'full' or 'worker'.")


def _tool_mode_backup_path(config_path: Path) -> Path:
    return config_path.with_name(f".{config_path.name}.agency-swarm-tool-mode.json")


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
    finally:
        try:
            path.chmod(0o600)
        except OSError:
            logger.debug("Could not chmod %s", path, exc_info=True)


def _read_tool_mode_backup(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read OpenClaw tool-mode backup at %s", path, exc_info=True)
        return None
    return raw if isinstance(raw, dict) else None


def _apply_tool_mode_config(current: dict[str, Any], tool_mode: str, config_path: Path) -> Path | None:
    if tool_mode == "worker":
        _apply_worker_tool_mode_config(current, _tool_mode_backup_path(config_path))
        return None

    backup_path = _tool_mode_backup_path(config_path)
    restored = _restore_full_tool_mode_config(current, backup_path, config_path)
    return backup_path if restored else None


def _apply_worker_tool_mode_config(current: dict[str, Any], backup_path: Path) -> None:
    existing_tools = current.get("tools")
    existing_agent_to_agent = existing_tools.get("agentToAgent") if isinstance(existing_tools, dict) else None
    existing_deny = existing_tools.get("deny") if isinstance(existing_tools, dict) else None

    if not backup_path.exists():
        _write_json_file(
            backup_path,
            {
                "had_tools": isinstance(existing_tools, dict),
                "agent_to_agent": existing_agent_to_agent if isinstance(existing_agent_to_agent, dict) else None,
                "deny": list(existing_deny) if isinstance(existing_deny, list) else None,
            },
        )

    tools = current.setdefault("tools", {})
    if not isinstance(tools, dict):
        tools = {}
        current["tools"] = tools

    agent_to_agent = tools.setdefault("agentToAgent", {})
    if not isinstance(agent_to_agent, dict):
        agent_to_agent = {}
        tools["agentToAgent"] = agent_to_agent
    agent_to_agent["enabled"] = False

    deny = tools.get("deny")
    if not isinstance(deny, list):
        deny = []

    for tool_name in ["message", "sessions_send", "sessions_spawn"]:
        if tool_name not in deny:
            deny.append(tool_name)
    tools["deny"] = deny


def _restore_full_tool_mode_config(current: dict[str, Any], backup_path: Path, config_path: Path) -> bool:
    backup = _read_tool_mode_backup(backup_path)
    if backup is None:
        return False

    tools = current.get("tools")
    if not isinstance(tools, dict):
        tools = {}
        current["tools"] = tools

    current_agent_to_agent = tools.get("agentToAgent")
    restored_agent_to_agent = backup.get("agent_to_agent")
    worker_agent_to_agent = backup.get("worker_agent_to_agent")
    if isinstance(restored_agent_to_agent, dict):
        if isinstance(worker_agent_to_agent, dict):
            if isinstance(current_agent_to_agent, dict):
                if current_agent_to_agent == worker_agent_to_agent:
                    tools["agentToAgent"] = restored_agent_to_agent.copy()
                else:
                    merged_agent_to_agent = restored_agent_to_agent.copy()
                    merged_agent_to_agent.update(current_agent_to_agent)
                    removed_agent_to_agent_keys = set(worker_agent_to_agent) - set(current_agent_to_agent)
                    for removed_key in removed_agent_to_agent_keys:
                        merged_agent_to_agent.pop(removed_key, None)
                    # If enabled still matches the worker-forced override, restore the backed-up
                    # full-mode value. A bare false here is ambiguous: it can mean "untouched worker
                    # override" or "user explicitly wants false", and the config file does not record
                    # which happened.
                    # We intentionally prefer the original full-mode setting unless the user changed
                    # enabled away from the worker snapshot.
                    if (
                        current_agent_to_agent.get("enabled") == worker_agent_to_agent.get("enabled")
                        and "enabled" in restored_agent_to_agent
                    ):
                        merged_agent_to_agent["enabled"] = restored_agent_to_agent["enabled"]
                    elif current_agent_to_agent.get("enabled") == worker_agent_to_agent.get("enabled"):
                        merged_agent_to_agent.pop("enabled", None)
                    tools["agentToAgent"] = merged_agent_to_agent
            else:
                tools.pop("agentToAgent", None)
        else:
            merged_agent_to_agent = restored_agent_to_agent.copy()
            if isinstance(current_agent_to_agent, dict):
                merged_agent_to_agent.update(current_agent_to_agent)
                tools["agentToAgent"] = merged_agent_to_agent
            else:
                tools.pop("agentToAgent", None)
    else:
        if isinstance(current_agent_to_agent, dict):
            current_agent_to_agent.pop("enabled", None)
            if current_agent_to_agent:
                tools["agentToAgent"] = current_agent_to_agent
            else:
                tools.pop("agentToAgent", None)
        else:
            tools.pop("agentToAgent", None)

    current_deny = tools.get("deny")
    restored_deny = backup.get("deny")
    worker_deny = backup.get("worker_deny")
    if isinstance(restored_deny, list):
        restored_deny_result = _restore_full_tool_mode_deny_list(
            current_deny=current_deny,
            restored_deny=restored_deny,
            worker_deny=worker_deny,
        )
        if restored_deny_result:
            tools["deny"] = restored_deny_result
        else:
            tools.pop("deny", None)
    else:
        restored_deny_result = _restore_full_tool_mode_deny_list(
            current_deny=current_deny,
            restored_deny=[],
            worker_deny=worker_deny,
        )
        if restored_deny_result:
            tools["deny"] = restored_deny_result
        else:
            tools.pop("deny", None)

    if not backup.get("had_tools") and not tools:
        current.pop("tools", None)
    return True


def _restore_full_tool_mode_deny_list(*, current_deny: Any, restored_deny: list[Any], worker_deny: Any) -> list[Any]:
    worker_only_denies = _worker_only_denies(restored_deny, worker_deny)
    if isinstance(current_deny, list) and isinstance(worker_deny, list) and current_deny == worker_deny:
        return restored_deny.copy()

    if not isinstance(current_deny, list):
        return []

    current_worker_only_denies = {item for item in current_deny if isinstance(item, str) and item in worker_only_denies}
    if current_worker_only_denies == worker_only_denies:
        return [item for item in current_deny if not (isinstance(item, str) and item in worker_only_denies)]

    return current_deny.copy()


def _record_worker_tool_mode_state(config_path: Path, backup_path: Path, current: dict[str, Any]) -> None:
    backup = _read_tool_mode_backup(backup_path)
    if backup is None:
        return
    updates: dict[str, Any] = {}

    tools = current.get("tools")
    agent_to_agent = tools.get("agentToAgent") if isinstance(tools, dict) else None
    deny = tools.get("deny") if isinstance(tools, dict) else None
    if "worker_agent_to_agent" not in backup:
        updates["worker_agent_to_agent"] = agent_to_agent if isinstance(agent_to_agent, dict) else None
    if "worker_deny" not in backup:
        updates["worker_deny"] = list(deny) if isinstance(deny, list) else None

    if not updates:
        return
    backup.update(updates)
    _write_json_file(backup_path, backup)


def _remove_tool_mode_backup(backup_path: Path) -> None:
    try:
        backup_path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        logger.warning("Could not remove OpenClaw tool-mode backup at %s", backup_path, exc_info=True)


def _worker_only_denies(restored_deny: list[Any], worker_deny: Any) -> set[str]:
    restored = {item for item in restored_deny if isinstance(item, str)}
    worker = {item for item in worker_deny if isinstance(item, str)} if isinstance(worker_deny, list) else set()
    if worker:
        return worker - restored
    return {"message", "sessions_send", "sessions_spawn"} - restored


def _is_upstream_port_open(config: OpenClawIntegrationConfig, timeout: float = 0.5) -> bool:
    try:
        addresses = socket.getaddrinfo(config.host, config.port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False

    for family, socktype, proto, _canonname, sockaddr in addresses:
        with socket.socket(family, socktype, proto) as sock:
            sock.settimeout(timeout)
            try:
                sock.connect(sockaddr)
                return True
            except OSError:
                continue
    return False


async def _close_stream_resources(stream_context: Any, client: httpx.AsyncClient) -> None:
    try:
        await stream_context.__aexit__(None, None, None)
    except Exception:
        logger.warning("OpenClaw stream context cleanup failed", exc_info=True)

    try:
        await client.aclose()
    except Exception:
        logger.warning("OpenClaw client cleanup failed", exc_info=True)


async def _stream_upstream(
    upstream: httpx.Response, stream_context: Any, client: httpx.AsyncClient
) -> AsyncIterator[bytes]:
    try:
        async for chunk in upstream.aiter_raw():
            if chunk:
                yield chunk
    finally:
        await _close_stream_resources(stream_context, client)


def create_openclaw_proxy_router(
    config: OpenClawIntegrationConfig,
    verify_token: Callable[..., Any] | None = None,
) -> APIRouter:
    """Create a FastAPI router exposing OpenClaw Open Responses proxy endpoints."""
    router = APIRouter()
    upstream_url = f"{config.upstream_base_url.rstrip('/')}/v1/responses"
    upstream_headers = _make_upstream_headers(config.gateway_token)
    response_dependencies = [Depends(verify_token)] if verify_token is not None else None

    @router.post("/v1/responses", dependencies=response_dependencies)
    async def proxy_responses(request: Request) -> Response:
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}") from exc

        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Request body must be a JSON object")

        try:
            normalized_payload = normalize_openclaw_responses_request(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        # Keep external model ID stable (`openclaw:main`) while routing upstream to
        # an explicit provider model selected for this deployment.
        if normalized_payload["model"] == config.default_model:
            normalized_payload["model"] = config.provider_model

        if not normalized_payload.get("stream"):
            try:
                async with httpx.AsyncClient(timeout=config.proxy_timeout_seconds) as client:
                    upstream = await client.post(upstream_url, headers=upstream_headers, json=normalized_payload)
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail=f"OpenClaw request failed: {exc}") from exc
            return _forward_response_passthrough(upstream)

        stream_timeout = httpx.Timeout(
            connect=config.proxy_timeout_seconds,
            read=None,
            write=config.proxy_timeout_seconds,
            pool=config.proxy_timeout_seconds,
        )
        client = httpx.AsyncClient(timeout=stream_timeout)
        stream_context = client.stream("POST", upstream_url, headers=upstream_headers, json=normalized_payload)
        try:
            upstream = await stream_context.__aenter__()
        except httpx.HTTPError as exc:
            try:
                await client.aclose()
            except Exception:
                logger.warning("OpenClaw client cleanup failed", exc_info=True)
            raise HTTPException(status_code=502, detail=f"OpenClaw stream connection failed: {exc}") from exc
        except Exception:
            try:
                await client.aclose()
            except Exception:
                logger.warning("OpenClaw client cleanup failed", exc_info=True)
            raise

        if upstream.status_code >= 400:
            try:
                body = await upstream.aread()
            finally:
                await _close_stream_resources(stream_context, client)
            headers = _passthrough_response_headers(upstream, decoded_body=True)
            content_type = headers.pop("content-type", "application/json")
            return Response(
                content=body,
                status_code=upstream.status_code,
                media_type=content_type,
                headers=headers,
            )

        response_headers = _passthrough_response_headers(upstream, decoded_body=False)
        response_content_type = response_headers.pop("content-type", "text/event-stream")
        return StreamingResponse(
            _stream_upstream(upstream, stream_context, client),
            status_code=upstream.status_code,
            media_type=response_content_type,
            headers=response_headers,
        )

    @router.get("/health", dependencies=response_dependencies)
    async def openclaw_proxy_health() -> JSONResponse:
        is_healthy = await asyncio.to_thread(_is_upstream_port_open, config)
        status_code = 200 if is_healthy else 503
        return JSONResponse({"ok": is_healthy, "upstream_base_url": config.upstream_base_url}, status_code=status_code)

    return router


def attach_openclaw_to_fastapi(
    app: FastAPI,
    config: OpenClawIntegrationConfig | None = None,
    verify_token: Callable[..., Any] | None = None,
) -> OpenClawRuntime:
    """Attach OpenClaw proxy routes and runtime lifecycle to a FastAPI app."""
    resolved_config = config or OpenClawIntegrationConfig.from_env()
    resolved_verify_token = verify_token or getattr(app.state, "verify_token", None)
    runtime = OpenClawRuntime(resolved_config)
    proxy_base_urls = _resolve_current_app_openclaw_proxy_base_urls(app)
    defaults_unregistered = False
    registered_urls: list[str] = []

    def _unregister_current_app_defaults() -> None:
        nonlocal defaults_unregistered
        if defaults_unregistered:
            return
        defaults_unregistered = True
        for url in registered_urls:
            openclaw_model.unregister_current_app_openclaw_defaults(base_url=url)

    try:
        for proxy_base_url in proxy_base_urls:
            openclaw_model.register_current_app_openclaw_defaults(
                default_model=resolved_config.default_model,
                provider_model=resolved_config.provider_model,
                base_url=proxy_base_url,
            )
            registered_urls.append(proxy_base_url)

        weakref.finalize(app, _unregister_current_app_defaults)

        app.include_router(
            create_openclaw_proxy_router(resolved_config, verify_token=resolved_verify_token),
            prefix="/openclaw",
            tags=["openclaw"],
        )
        app.state.openclaw_runtime = runtime
        app.state.openclaw_config = resolved_config

        existing_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def _openclaw_lifespan(inner_app: FastAPI) -> AsyncIterator[Any]:
            async with existing_lifespan(inner_app) as lifespan_state:
                should_stop_runtime = False
                if resolved_config.autostart:
                    await asyncio.to_thread(runtime.start)
                    should_stop_runtime = True
                else:
                    logger.info("OpenClaw runtime autostart disabled")
                try:
                    yield lifespan_state
                finally:
                    _unregister_current_app_defaults()
                    if should_stop_runtime:
                        await asyncio.to_thread(runtime.stop)

        app.router.lifespan_context = _openclaw_lifespan

        return runtime
    except Exception:
        _unregister_current_app_defaults()
        raise


def _resolve_current_app_openclaw_proxy_base_urls(app: FastAPI) -> list[str]:
    proxy_base_urls: list[str] = []
    if openclaw_model._has_explicit_openclaw_proxy_base_url():
        proxy_base_urls.append(openclaw_model._resolve_current_openclaw_proxy_base_url())
    servers = getattr(app, "servers", None)
    if isinstance(servers, list):
        for server in servers:
            if not isinstance(server, dict):
                continue
            server_url = server.get("url")
            if isinstance(server_url, str) and server_url.strip():
                proxy_base_urls.append(f"{server_url.rstrip('/')}{DEFAULT_OPENCLAW_PROXY_API_PATH}")

    # Preserve insertion order while deduplicating equivalent URLs.
    deduped: dict[tuple[str, str, int, str], str] = {}
    for proxy_base_url in proxy_base_urls:
        normalized = openclaw_model._normalize_openclaw_proxy_url(proxy_base_url)
        deduped.setdefault(normalized, proxy_base_url)
    return list(deduped.values())


def build_openclaw_responses_model(
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> OpenAIResponsesModel:
    """Build an OpenAIResponsesModel that targets the mounted OpenClaw proxy."""
    return openclaw_model.build_openclaw_responses_model(model=model, base_url=base_url, api_key=api_key)

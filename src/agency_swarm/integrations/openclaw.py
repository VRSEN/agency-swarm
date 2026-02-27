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
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from agents import OpenAIResponsesModel
from dotenv import dotenv_values
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

DEFAULT_OPENCLAW_MODEL = "openclaw:main"

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


def _read_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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

    @property
    def upstream_base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @classmethod
    def from_env(cls) -> OpenClawIntegrationConfig:
        home_dir = Path(os.getenv("OPENCLAW_HOME", "/mnt/openclaw")).expanduser().resolve()
        state_dir = Path(os.getenv("OPENCLAW_STATE_DIR", str(home_dir / "state"))).expanduser().resolve()
        config_path = Path(os.getenv("OPENCLAW_CONFIG_PATH", str(home_dir / "openclaw.json"))).expanduser().resolve()
        log_path = (
            Path(os.getenv("OPENCLAW_LOG_PATH", str(home_dir / "logs" / "openclaw-gateway.log"))).expanduser().resolve()
        )

        return cls(
            autostart=_read_bool_env("OPENCLAW_AUTOSTART", default=True),
            host=os.getenv("OPENCLAW_HOST", "127.0.0.1"),
            port=int(os.getenv("OPENCLAW_PORT", "18789")),
            gateway_token=os.getenv("OPENCLAW_GATEWAY_TOKEN", "openclaw-local-token"),
            home_dir=home_dir,
            state_dir=state_dir,
            config_path=config_path,
            log_path=log_path,
            startup_timeout_seconds=float(os.getenv("OPENCLAW_STARTUP_TIMEOUT_SECONDS", "60")),
            proxy_timeout_seconds=float(os.getenv("OPENCLAW_PROXY_TIMEOUT_SECONDS", "120")),
            default_model=os.getenv("OPENCLAW_DEFAULT_MODEL", DEFAULT_OPENCLAW_MODEL),
            provider_model=os.getenv("OPENCLAW_PROVIDER_MODEL", "openai/gpt-4o-mini"),
            gateway_command=os.getenv("OPENCLAW_GATEWAY_COMMAND"),
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
            if not isinstance(key, str) or not key.endswith("_API_KEY"):
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

        self.config.config_path.write_text(json.dumps(current, indent=2), encoding="utf-8")

    def _resolve_gateway_command(self) -> list[str]:
        if self.config.gateway_command:
            command = shlex.split(self.config.gateway_command)
        elif shutil.which("openclaw"):
            command = ["openclaw", "gateway"]
        else:
            raise RuntimeError(
                "OpenClaw runtime unavailable. Install a pinned `openclaw` binary "
                "or set OPENCLAW_GATEWAY_COMMAND to a deterministic command."
            )

        if "--port" not in command:
            command.extend(["--port", str(self.config.port)])
        return command

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
            return

        self.ensure_layout()
        command = self._resolve_gateway_command()

        env = os.environ.copy()
        env["OPENCLAW_HOME"] = str(self.config.home_dir)
        env["OPENCLAW_STATE_DIR"] = str(self.config.state_dir)
        env["OPENCLAW_CONFIG_PATH"] = str(self.config.config_path)
        env["OPENCLAW_LOG_PATH"] = str(self.config.log_path)
        env["OPENCLAW_GATEWAY_TOKEN"] = self.config.gateway_token

        self._merge_provider_keys_from_dotenv(env)

        missing_provider_keys = [key for key in _PROVIDER_ENV_KEYS if not env.get(key)]
        if len(missing_provider_keys) == len(_PROVIDER_ENV_KEYS):
            logger.warning("No provider API keys found in env (checked: %s)", ", ".join(_PROVIDER_ENV_KEYS))

        self._log_handle = self.config.log_path.open("ab", buffering=0)
        self._process = subprocess.Popen(
            command,
            cwd=str(self.config.home_dir),
            env=env,
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        deadline = time.time() + self.config.startup_timeout_seconds
        while time.time() < deadline:
            if self._process.poll() is not None:
                raise RuntimeError(
                    f"OpenClaw exited early with code {self._process.returncode}. Check logs at {self.config.log_path}."
                )
            if self._is_port_open():
                logger.info("OpenClaw runtime listening at %s", self.upstream_base_url)
                return
            time.sleep(0.4)

        raise TimeoutError(f"Timed out waiting for OpenClaw at {self.upstream_base_url}")

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
            process.wait(timeout=5)
        finally:
            if self._log_handle is not None:
                self._log_handle.close()
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
    if not isinstance(tools, list):
        return []

    normalized_tools: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue

        function_payload = tool.get("function")
        function_name: str | None = None
        function_description: str | None = None
        function_parameters: dict[str, Any] | None = None

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

        if function_name is None:
            raw_name = tool.get("name")
            if isinstance(raw_name, str) and raw_name:
                function_name = raw_name

        if function_name is None:
            continue

        normalized_function: dict[str, Any] = {"name": function_name}
        if function_description is not None:
            normalized_function["description"] = function_description
        if function_parameters is not None:
            normalized_function["parameters"] = function_parameters
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
        normalized[key] = json.dumps(value, ensure_ascii=False)
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


def _forward_response_passthrough(upstream: httpx.Response) -> Response:
    content_type = upstream.headers.get("content-type", "application/json")
    return Response(content=upstream.content, status_code=upstream.status_code, media_type=content_type)


async def _stream_upstream(
    upstream: httpx.Response, stream_context: Any, client: httpx.AsyncClient
) -> AsyncIterator[bytes]:
    try:
        async for chunk in upstream.aiter_raw():
            if chunk:
                yield chunk
    finally:
        await stream_context.__aexit__(None, None, None)
        await client.aclose()


def create_openclaw_proxy_router(config: OpenClawIntegrationConfig) -> APIRouter:
    """Create a FastAPI router exposing OpenClaw Open Responses proxy endpoints."""
    router = APIRouter()
    upstream_url = f"{config.upstream_base_url.rstrip('/')}/v1/responses"
    upstream_headers = _make_upstream_headers(config.gateway_token)

    @router.post("/v1/responses")
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

        client = httpx.AsyncClient(timeout=None)
        stream_context = client.stream("POST", upstream_url, headers=upstream_headers, json=normalized_payload)
        try:
            upstream = await stream_context.__aenter__()
        except httpx.HTTPError as exc:
            await client.aclose()
            raise HTTPException(status_code=502, detail=f"OpenClaw stream connection failed: {exc}") from exc

        if upstream.status_code >= 400:
            try:
                body = await upstream.aread()
            finally:
                await stream_context.__aexit__(None, None, None)
                await client.aclose()
            return Response(
                content=body,
                status_code=upstream.status_code,
                media_type=upstream.headers.get("content-type", "application/json"),
            )

        return StreamingResponse(
            _stream_upstream(upstream, stream_context, client),
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "text/event-stream"),
        )

    @router.get("/health")
    async def openclaw_proxy_health() -> JSONResponse:
        return JSONResponse({"ok": True, "upstream_base_url": config.upstream_base_url})

    return router


def attach_openclaw_to_fastapi(
    app: FastAPI,
    config: OpenClawIntegrationConfig | None = None,
) -> OpenClawRuntime:
    """Attach OpenClaw proxy routes and runtime lifecycle to a FastAPI app."""
    resolved_config = config or OpenClawIntegrationConfig.from_env()
    runtime = OpenClawRuntime(resolved_config)

    app.include_router(create_openclaw_proxy_router(resolved_config), prefix="/openclaw", tags=["openclaw"])
    app.state.openclaw_runtime = runtime
    app.state.openclaw_config = resolved_config

    @app.on_event("startup")
    async def _startup_openclaw_runtime() -> None:
        if resolved_config.autostart:
            runtime.start()
        else:
            logger.info("OpenClaw runtime autostart disabled")

    @app.on_event("shutdown")
    async def _shutdown_openclaw_runtime() -> None:
        runtime.stop()

    return runtime


def build_openclaw_responses_model(
    model: str = DEFAULT_OPENCLAW_MODEL,
    base_url: str | None = None,
    api_key: str | None = None,
) -> OpenAIResponsesModel:
    """Build an OpenAIResponsesModel that targets the mounted OpenClaw proxy."""
    resolved_base_url = (
        base_url or os.getenv("OPENCLAW_PROXY_BASE_URL") or "http://127.0.0.1:8000/openclaw/v1"
    ).rstrip("/")
    resolved_api_key = api_key or os.getenv("OPENCLAW_PROXY_API_KEY") or "sk-openclaw-proxy"

    client = AsyncOpenAI(base_url=resolved_base_url, api_key=resolved_api_key)
    return OpenAIResponsesModel(model=model, openai_client=client)

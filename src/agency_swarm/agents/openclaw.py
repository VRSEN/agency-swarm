from __future__ import annotations

import os
from typing import Any

import httpx

from agency_swarm.agent.core import Agent
from agency_swarm.integrations.openclaw_model import build_openclaw_responses_model

DEFAULT_OPENCLAW_API_PATH = "/openclaw/v1"


class OpenClawAgent(Agent):
    """Agency Swarm agent wrapper for an OpenClaw worker."""

    supports_outbound_communication = False
    supports_framework_tool_wiring = False

    def __init__(
        self,
        *,
        base_url: str | None = None,
        host: str | None = None,
        port: int | None = None,
        api_path: str = DEFAULT_OPENCLAW_API_PATH,
        api_key: str | None = None,
        **kwargs: Any,
    ) -> None:
        resolved_model = _pop_openclaw_model_override(kwargs)
        _validate_openclaw_agent_kwargs(kwargs)
        resolved_base_url = _resolve_openclaw_base_url(
            base_url=base_url,
            host=host,
            port=port,
            api_path=api_path,
        )

        kwargs["model"] = build_openclaw_responses_model(
            model=resolved_model,
            base_url=resolved_base_url,
            api_key=api_key,
        )
        super().__init__(**kwargs)


def _resolve_openclaw_base_url(
    *,
    base_url: str | None,
    host: str | None,
    port: int | None,
    api_path: str,
) -> str:
    if base_url:
        return base_url.rstrip("/")

    env_base_url = os.getenv("OPENCLAW_PROXY_BASE_URL", "").strip()
    if env_base_url:
        if host is None and port is None and api_path == DEFAULT_OPENCLAW_API_PATH:
            return env_base_url.rstrip("/")
        parsed_env_base_url = httpx.URL(env_base_url.rstrip("/"))
        normalized_api_path = api_path if api_path.startswith("/") else f"/{api_path}"
        resolved_base_url = parsed_env_base_url.copy_with(
            host=host or parsed_env_base_url.host,
            port=port or parsed_env_base_url.port,
            path=normalized_api_path if api_path != DEFAULT_OPENCLAW_API_PATH else parsed_env_base_url.path,
        )
        return str(resolved_base_url).rstrip("/")

    if host is not None or port is not None or api_path != DEFAULT_OPENCLAW_API_PATH:
        resolved_host = _normalize_http_host(host or os.getenv("OPENCLAW_PROXY_HOST") or "127.0.0.1")
        resolved_port = port or int(os.getenv("OPENCLAW_PROXY_PORT") or os.getenv("PORT") or "8000")
        normalized_api_path = api_path if api_path.startswith("/") else f"/{api_path}"
        return f"http://{resolved_host}:{resolved_port}{normalized_api_path}".rstrip("/")

    resolved_host = _normalize_http_host(host or os.getenv("OPENCLAW_PROXY_HOST") or "127.0.0.1")
    resolved_port = port or int(os.getenv("OPENCLAW_PROXY_PORT") or os.getenv("PORT") or "8000")
    normalized_api_path = api_path if api_path.startswith("/") else f"/{api_path}"
    return f"http://{resolved_host}:{resolved_port}{normalized_api_path}".rstrip("/")


def _normalize_http_host(host: str) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def _pop_openclaw_model_override(kwargs: dict[str, Any]) -> str | None:
    model = kwargs.pop("model", None)
    if model is None:
        return None
    if not isinstance(model, str) or not model.strip():
        raise TypeError("OpenClawAgent only accepts non-empty string model aliases.")
    return model.strip()


def _validate_openclaw_agent_kwargs(kwargs: dict[str, Any]) -> None:
    if kwargs.get("handoffs"):
        raise TypeError(
            "OpenClawAgent does not accept manual handoffs. Use a normal Agency Swarm agent as the delegator."
        )

    if "supports_outbound_communication" in kwargs or "supports_framework_tool_wiring" in kwargs:
        raise TypeError(
            "OpenClawAgent is always receive-only and manages its worker wiring automatically. "
            "Remove communication capability overrides."
        )

    unsupported_fields = [
        key
        for key in (
            "tools",
            "files_folder",
            "tools_folder",
            "schemas_folder",
            "mcp_servers",
            "api_headers",
            "api_params",
        )
        if key in kwargs and kwargs[key]
    ]
    if unsupported_fields:
        joined = ", ".join(unsupported_fields)
        raise TypeError(
            "OpenClawAgent does not accept Agency Swarm tool wiring "
            f"({joined}). Use OpenClaw plugins or MCP to extend OpenClaw itself."
        )

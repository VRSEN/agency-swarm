from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from agents.models.openai_responses import OpenAIResponsesModel
from openai import AsyncOpenAI

from agency_swarm.agent.core import Agent

DEFAULT_OPENCLAW_API_PATH = "/openclaw/v1"
DEFAULT_OPENCLAW_MODEL = "openclaw:main"


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
        _validate_openclaw_agent_kwargs(kwargs)
        resolved_base_url = _resolve_openclaw_base_url(
            base_url=base_url,
            host=host,
            port=port,
            api_path=api_path,
        )

        kwargs["model"] = _build_openclaw_responses_model(base_url=resolved_base_url, api_key=api_key)
        super().__init__(**kwargs)


def _build_openclaw_responses_model(*, base_url: str, api_key: str | None) -> OpenAIResponsesModel:
    client = AsyncOpenAI(base_url=base_url, api_key=_resolve_openclaw_api_key(api_key))
    return OpenAIResponsesModel(
        model=_resolve_openclaw_model(base_url),
        openai_client=client,
    )


def _resolve_openclaw_model(base_url: str) -> str:
    if _uses_local_proxy_alias(base_url):
        return os.getenv("OPENCLAW_DEFAULT_MODEL", "").strip() or DEFAULT_OPENCLAW_MODEL
    return os.getenv("OPENCLAW_DEFAULT_MODEL", "").strip() or DEFAULT_OPENCLAW_MODEL


def _resolve_openclaw_api_key(api_key: str | None) -> str:
    return (
        api_key
        or os.getenv("OPENCLAW_PROXY_API_KEY")
        or os.getenv("APP_TOKEN")
        or os.getenv("OPENCLAW_GATEWAY_TOKEN")
        or "sk-openclaw-proxy"
    )


def _uses_local_proxy_alias(base_url: str) -> bool:
    parsed = urlparse(base_url)
    normalized_path = parsed.path.rstrip("/")
    return normalized_path.endswith(DEFAULT_OPENCLAW_API_PATH) or "/openclaw/" in normalized_path


def _resolve_openclaw_base_url(
    *,
    base_url: str | None,
    host: str | None,
    port: int | None,
    api_path: str,
) -> str:
    if base_url:
        return base_url.rstrip("/")

    if host is not None or port is not None or api_path != DEFAULT_OPENCLAW_API_PATH:
        resolved_host = host or os.getenv("OPENCLAW_PROXY_HOST") or "127.0.0.1"
        resolved_port = port or int(os.getenv("OPENCLAW_PROXY_PORT") or os.getenv("PORT") or "8000")
        normalized_api_path = api_path if api_path.startswith("/") else f"/{api_path}"
        return f"http://{resolved_host}:{resolved_port}{normalized_api_path}".rstrip("/")

    env_base_url = os.getenv("OPENCLAW_PROXY_BASE_URL", "").strip()
    if env_base_url:
        return env_base_url.rstrip("/")

    resolved_host = host or os.getenv("OPENCLAW_PROXY_HOST") or "127.0.0.1"
    resolved_port = port or int(os.getenv("OPENCLAW_PROXY_PORT") or os.getenv("PORT") or "8000")
    normalized_api_path = api_path if api_path.startswith("/") else f"/{api_path}"
    return f"http://{resolved_host}:{resolved_port}{normalized_api_path}".rstrip("/")


def _validate_openclaw_agent_kwargs(kwargs: dict[str, Any]) -> None:
    if "model" in kwargs:
        raise TypeError("OpenClawAgent configures its model automatically. Remove the 'model' argument.")

    if kwargs.get("handoffs"):
        raise TypeError(
            "OpenClawAgent does not accept manual handoffs. Use a normal Agency Swarm agent as the delegator."
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

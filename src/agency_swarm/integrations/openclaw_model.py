from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from typing import Protocol, cast

import httpx
from agents import OpenAIResponsesModel
from openai import AsyncOpenAI

DEFAULT_OPENCLAW_MODEL = "openclaw:main"
DEFAULT_OPENCLAW_PROXY_API_PATH = "/openclaw/v1"
DEFAULT_OPENCLAW_PROVIDER_MODEL = "openai/gpt-5.4"


@dataclass(frozen=True)
class _CurrentAppOpenClawDefaults:
    default_model: str
    provider_model: str


_CURRENT_APP_OPENCLAW_DEFAULTS: dict[tuple[str, str, int, str], _CurrentAppOpenClawDefaults] = {}


def build_openclaw_responses_model(
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> OpenAIResponsesModel:
    resolved_base_url = (base_url or _resolve_current_openclaw_proxy_base_url()).rstrip("/")

    if isinstance(model, str) and model.strip():
        resolved_model = model.strip()
    else:
        resolved_model = _resolve_openclaw_default_model(resolved_base_url)
    resolved_usage_model = _resolve_openclaw_usage_model(resolved_model, resolved_base_url)
    resolved_api_key = _resolve_openclaw_responses_api_key(resolved_base_url, api_key)

    client = AsyncOpenAI(base_url=resolved_base_url, api_key=resolved_api_key)
    responses_model = OpenAIResponsesModel(model=resolved_model, openai_client=client)
    if resolved_usage_model is not None:
        cast(_ResponsesModelWithUsageName, responses_model)._agency_swarm_usage_model_name = resolved_usage_model
    cast(
        _ResponsesModelWithDefaultSettingsName, responses_model
    )._agency_swarm_default_model_name = _resolve_openclaw_default_settings_model_name(
        resolved_usage_model or resolved_model
    )
    return responses_model


def _resolve_openclaw_usage_model(model_name: str, base_url: str) -> str | None:
    if model_name.startswith("openclaw:"):
        current_app_defaults = _resolve_current_app_openclaw_defaults(base_url)
        if current_app_defaults is not None:
            return current_app_defaults.provider_model
        if _uses_raw_openclaw_gateway(base_url):
            return os.getenv("OPENCLAW_PROVIDER_MODEL", "").strip() or DEFAULT_OPENCLAW_PROVIDER_MODEL
        if _uses_current_app_openclaw_proxy(base_url):
            return os.getenv("OPENCLAW_PROVIDER_MODEL", "").strip() or DEFAULT_OPENCLAW_PROVIDER_MODEL
        return model_name
    return model_name


def _resolve_openclaw_default_model(base_url: str) -> str:
    env_default_model = os.getenv("OPENCLAW_DEFAULT_MODEL", "").strip()
    if _uses_raw_openclaw_gateway(base_url):
        if env_default_model and not env_default_model.startswith("openclaw:"):
            return env_default_model
        return os.getenv("OPENCLAW_PROVIDER_MODEL", "").strip() or DEFAULT_OPENCLAW_PROVIDER_MODEL
    current_app_defaults = _resolve_current_app_openclaw_defaults(base_url)
    if current_app_defaults is not None:
        return current_app_defaults.default_model
    if env_default_model:
        return env_default_model
    return DEFAULT_OPENCLAW_MODEL


def _resolve_openclaw_responses_api_key(base_url: str, api_key: str | None) -> str:
    if api_key:
        return api_key

    if _uses_current_app_openclaw_proxy(base_url):
        return (
            os.getenv("APP_TOKEN")
            or os.getenv("OPENCLAW_PROXY_API_KEY")
            or os.getenv("OPENCLAW_GATEWAY_TOKEN")
            or "sk-openclaw-proxy"
        )

    if _uses_raw_openclaw_gateway(base_url):
        return os.getenv("OPENCLAW_GATEWAY_TOKEN") or os.getenv("OPENCLAW_PROXY_API_KEY") or "sk-openclaw-proxy"

    proxy_api_key = os.getenv("OPENCLAW_PROXY_API_KEY")
    if proxy_api_key:
        return proxy_api_key

    return os.getenv("OPENCLAW_GATEWAY_TOKEN") or "sk-openclaw-proxy"


def _uses_current_app_openclaw_proxy(base_url: str) -> bool:
    if _resolve_current_app_openclaw_defaults(base_url) is not None:
        return True
    return _normalize_openclaw_proxy_url(base_url) == _normalize_openclaw_proxy_url(
        _resolve_current_openclaw_proxy_base_url()
    )


def register_current_app_openclaw_defaults(
    default_model: str,
    provider_model: str,
    *,
    base_url: str | None = None,
) -> None:
    global _CURRENT_APP_OPENCLAW_DEFAULTS
    proxy_base_url = _normalize_openclaw_proxy_url(base_url or _resolve_current_openclaw_proxy_base_url())
    new_defaults = _CurrentAppOpenClawDefaults(
        default_model=default_model.strip() or DEFAULT_OPENCLAW_MODEL,
        provider_model=provider_model.strip() or DEFAULT_OPENCLAW_PROVIDER_MODEL,
    )
    existing_defaults = _CURRENT_APP_OPENCLAW_DEFAULTS.get(proxy_base_url)
    if existing_defaults is not None and existing_defaults != new_defaults:
        raise ValueError(
            "Conflicting current-app OpenClaw defaults for the same proxy base URL. "
            "Use one current-app proxy config per process or set distinct proxy base URLs."
        )
    _CURRENT_APP_OPENCLAW_DEFAULTS[proxy_base_url] = new_defaults


def _resolve_current_openclaw_proxy_base_url() -> str:
    env_base_url = os.getenv("OPENCLAW_PROXY_BASE_URL", "").strip()
    if env_base_url:
        return env_base_url.rstrip("/")

    host = os.getenv("OPENCLAW_PROXY_HOST") or "127.0.0.1"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = os.getenv("OPENCLAW_PROXY_PORT") or os.getenv("PORT") or "8000"
    return f"http://{host}:{port}{DEFAULT_OPENCLAW_PROXY_API_PATH}".rstrip("/")


def _uses_raw_openclaw_gateway(base_url: str) -> bool:
    parsed = httpx.URL(base_url)
    normalized_path = parsed.path.rstrip("/")
    return normalized_path == "/v1"


def _normalize_openclaw_proxy_url(base_url: str) -> tuple[str, str, int, str]:
    parsed = httpx.URL(base_url)
    hostname = parsed.host or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    normalized_path = parsed.path.rstrip("/")
    return parsed.scheme, _normalize_openclaw_proxy_host(hostname), port, normalized_path


def _normalize_openclaw_proxy_host(hostname: str) -> str:
    lowered = hostname.lower()
    if lowered in {"localhost", "localhost.localdomain"}:
        return "loopback"
    try:
        return "loopback" if ipaddress.ip_address(hostname).is_loopback else lowered
    except ValueError:
        return lowered


def _get_current_app_openclaw_defaults(base_url: str) -> _CurrentAppOpenClawDefaults | None:
    return _CURRENT_APP_OPENCLAW_DEFAULTS.get(_normalize_openclaw_proxy_url(base_url))


def _resolve_current_app_openclaw_defaults(base_url: str) -> _CurrentAppOpenClawDefaults | None:
    return _get_current_app_openclaw_defaults(base_url)


def _resolve_openclaw_default_settings_model_name(model_name: str) -> str:
    if "/" in model_name:
        _, _, bare_model_name = model_name.rpartition("/")
        return bare_model_name or model_name
    return model_name


class _ResponsesModelWithUsageName(Protocol):
    _agency_swarm_usage_model_name: str


class _ResponsesModelWithDefaultSettingsName(Protocol):
    _agency_swarm_default_model_name: str

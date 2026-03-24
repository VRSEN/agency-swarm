from __future__ import annotations

import os
from typing import Protocol, cast

import httpx
from agents import OpenAIResponsesModel
from openai import AsyncOpenAI

DEFAULT_OPENCLAW_MODEL = "openclaw:main"
DEFAULT_OPENCLAW_PROXY_API_PATH = "/openclaw/v1"
DEFAULT_OPENCLAW_PROVIDER_MODEL = "openai/gpt-5.4"


def build_openclaw_responses_model(
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> OpenAIResponsesModel:
    resolved_base_url = (
        base_url or os.getenv("OPENCLAW_PROXY_BASE_URL") or f"http://127.0.0.1:8000{DEFAULT_OPENCLAW_PROXY_API_PATH}"
    ).rstrip("/")

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
    return responses_model


def _resolve_openclaw_usage_model(model_name: str, base_url: str) -> str | None:
    if model_name.startswith("openclaw:"):
        provider_model = os.getenv("OPENCLAW_PROVIDER_MODEL", "").strip()
        if provider_model:
            return provider_model
        if _uses_current_app_openclaw_proxy(base_url):
            return DEFAULT_OPENCLAW_PROVIDER_MODEL
        return None
    return model_name


def _resolve_openclaw_default_model(base_url: str) -> str:
    env_default_model = os.getenv("OPENCLAW_DEFAULT_MODEL", "").strip()
    if env_default_model:
        return env_default_model
    if _uses_raw_openclaw_gateway(base_url):
        return os.getenv("OPENCLAW_PROVIDER_MODEL", "").strip() or DEFAULT_OPENCLAW_PROVIDER_MODEL
    return DEFAULT_OPENCLAW_MODEL


def _resolve_openclaw_responses_api_key(base_url: str, api_key: str | None) -> str:
    if api_key:
        return api_key

    proxy_api_key = os.getenv("OPENCLAW_PROXY_API_KEY")
    if proxy_api_key:
        return proxy_api_key

    if _uses_current_app_openclaw_proxy(base_url):
        return os.getenv("APP_TOKEN") or os.getenv("OPENCLAW_GATEWAY_TOKEN") or "sk-openclaw-proxy"

    return os.getenv("OPENCLAW_GATEWAY_TOKEN") or "sk-openclaw-proxy"


def _uses_current_app_openclaw_proxy(base_url: str) -> bool:
    return base_url.rstrip("/") == _resolve_current_openclaw_proxy_base_url()


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


class _ResponsesModelWithUsageName(Protocol):
    _agency_swarm_usage_model_name: str

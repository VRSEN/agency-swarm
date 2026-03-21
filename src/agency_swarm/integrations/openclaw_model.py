from __future__ import annotations

import os

import httpx
from agents import OpenAIResponsesModel
from openai import AsyncOpenAI

DEFAULT_OPENCLAW_MODEL = "openclaw:main"
DEFAULT_OPENCLAW_PROXY_API_PATH = "/openclaw/v1"


def build_openclaw_responses_model(
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> OpenAIResponsesModel:
    if isinstance(model, str) and model.strip():
        resolved_model = model.strip()
    else:
        env_default_model = os.getenv("OPENCLAW_DEFAULT_MODEL", "").strip()
        resolved_model = env_default_model or DEFAULT_OPENCLAW_MODEL

    resolved_base_url = (
        base_url or os.getenv("OPENCLAW_PROXY_BASE_URL") or f"http://127.0.0.1:8000{DEFAULT_OPENCLAW_PROXY_API_PATH}"
    ).rstrip("/")
    resolved_api_key = _resolve_openclaw_responses_api_key(resolved_base_url, api_key)

    client = AsyncOpenAI(base_url=resolved_base_url, api_key=resolved_api_key)
    return OpenAIResponsesModel(model=resolved_model, openai_client=client)


def _resolve_openclaw_responses_api_key(base_url: str, api_key: str | None) -> str:
    if api_key:
        return api_key

    proxy_api_key = os.getenv("OPENCLAW_PROXY_API_KEY")
    if proxy_api_key:
        return proxy_api_key

    if _uses_local_openclaw_proxy_alias(base_url):
        return os.getenv("APP_TOKEN") or os.getenv("OPENCLAW_GATEWAY_TOKEN") or "sk-openclaw-proxy"

    return os.getenv("OPENCLAW_GATEWAY_TOKEN") or os.getenv("APP_TOKEN") or "sk-openclaw-proxy"


def _uses_local_openclaw_proxy_alias(base_url: str) -> bool:
    parsed = httpx.URL(base_url)
    if parsed.host not in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}:
        return False
    normalized_path = parsed.path.rstrip("/")
    return normalized_path.endswith(DEFAULT_OPENCLAW_PROXY_API_PATH) or "/openclaw/" in normalized_path

from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass
from typing import Protocol, cast

import httpx
from agents import OpenAIResponsesModel
from openai import AsyncOpenAI

DEFAULT_OPENCLAW_MODEL = "openclaw:main"
DEFAULT_OPENCLAW_PROXY_API_PATH = "/openclaw/v1"
DEFAULT_OPENCLAW_PROVIDER_MODEL = "openai/gpt-5.4"
DEFAULT_OPENCLAW_LOCAL_GATEWAY_TOKEN = "openclaw-local-token"


@dataclass(frozen=True)
class _CurrentAppOpenClawDefaults:
    default_model: str
    provider_model: str


@dataclass(frozen=True)
class _CurrentAppOpenClawDefaultsPattern:
    scheme: str | None
    host_pattern: str | None
    port: int | None
    path_pattern: str


_CURRENT_APP_OPENCLAW_DEFAULTS: dict[tuple[str, str, int, str], _CurrentAppOpenClawDefaults] = {}
_CURRENT_APP_OPENCLAW_DEFAULT_COUNTS: dict[tuple[str, str, int, str], int] = {}
_CURRENT_APP_OPENCLAW_DEFAULT_PATTERNS: list[
    tuple[_CurrentAppOpenClawDefaultsPattern, _CurrentAppOpenClawDefaults]
] = []
_CURRENT_APP_OPENCLAW_DEFAULT_PATTERN_COUNTS: dict[_CurrentAppOpenClawDefaultsPattern, int] = {}


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
            if model_name == current_app_defaults.default_model:
                return current_app_defaults.provider_model
            return model_name
        if _uses_raw_openclaw_gateway(base_url):
            return model_name
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
        return (
            os.getenv("OPENCLAW_GATEWAY_TOKEN")
            or os.getenv("OPENCLAW_PROXY_API_KEY")
            or os.getenv("APP_TOKEN")
            or DEFAULT_OPENCLAW_LOCAL_GATEWAY_TOKEN
        )

    proxy_api_key = os.getenv("OPENCLAW_PROXY_API_KEY")
    if proxy_api_key:
        return proxy_api_key

    return os.getenv("OPENCLAW_GATEWAY_TOKEN") or "sk-openclaw-proxy"


def _uses_current_app_openclaw_proxy(base_url: str) -> bool:
    if _resolve_current_app_openclaw_defaults(base_url) is not None:
        return True
    current_proxy_base_url = _normalize_openclaw_proxy_url(_resolve_current_openclaw_proxy_base_url())
    return (
        _is_loopback_openclaw_proxy_url(current_proxy_base_url)
        and _normalize_openclaw_proxy_url(base_url) == current_proxy_base_url
    )


def register_current_app_openclaw_defaults(
    default_model: str,
    provider_model: str,
    *,
    base_url: str | None = None,
) -> None:
    global _CURRENT_APP_OPENCLAW_DEFAULTS
    global _CURRENT_APP_OPENCLAW_DEFAULT_PATTERNS
    proxy_base_url = _normalize_current_app_openclaw_proxy_matcher(
        base_url or _resolve_current_openclaw_proxy_base_url()
    )
    new_defaults = _CurrentAppOpenClawDefaults(
        default_model=default_model.strip() or DEFAULT_OPENCLAW_MODEL,
        provider_model=provider_model.strip() or DEFAULT_OPENCLAW_PROVIDER_MODEL,
    )
    if isinstance(proxy_base_url, tuple):
        existing_defaults = _CURRENT_APP_OPENCLAW_DEFAULTS.get(proxy_base_url)
        if existing_defaults is not None and existing_defaults != new_defaults:
            raise ValueError(
                "Conflicting current-app OpenClaw defaults for the same proxy base URL. "
                "Use one current-app proxy config per process or set distinct proxy base URLs."
            )
        _CURRENT_APP_OPENCLAW_DEFAULTS[proxy_base_url] = new_defaults
        _CURRENT_APP_OPENCLAW_DEFAULT_COUNTS[proxy_base_url] = (
            _CURRENT_APP_OPENCLAW_DEFAULT_COUNTS.get(proxy_base_url, 0) + 1
        )
        return

    if proxy_base_url.scheme is None or proxy_base_url.host_pattern is None or proxy_base_url.port is None:
        return

    for existing_pattern, existing_defaults in _CURRENT_APP_OPENCLAW_DEFAULT_PATTERNS:
        if existing_pattern != proxy_base_url:
            continue
        if existing_defaults != new_defaults:
            raise ValueError(
                "Conflicting current-app OpenClaw defaults for the same proxy base URL. "
                "Use one current-app proxy config per process or set distinct proxy base URLs."
            )
        _CURRENT_APP_OPENCLAW_DEFAULT_PATTERN_COUNTS[proxy_base_url] = (
            _CURRENT_APP_OPENCLAW_DEFAULT_PATTERN_COUNTS.get(proxy_base_url, 0) + 1
        )
        return

    _CURRENT_APP_OPENCLAW_DEFAULT_PATTERNS.append((proxy_base_url, new_defaults))
    _CURRENT_APP_OPENCLAW_DEFAULT_PATTERN_COUNTS[proxy_base_url] = 1


def unregister_current_app_openclaw_defaults(*, base_url: str) -> None:
    global _CURRENT_APP_OPENCLAW_DEFAULT_PATTERNS
    proxy_base_url = _normalize_current_app_openclaw_proxy_matcher(base_url)
    if isinstance(proxy_base_url, tuple):
        registration_count = _CURRENT_APP_OPENCLAW_DEFAULT_COUNTS.get(proxy_base_url)
        if registration_count is None:
            return
        if registration_count > 1:
            _CURRENT_APP_OPENCLAW_DEFAULT_COUNTS[proxy_base_url] = registration_count - 1
            return
        _CURRENT_APP_OPENCLAW_DEFAULT_COUNTS.pop(proxy_base_url, None)
        _CURRENT_APP_OPENCLAW_DEFAULTS.pop(proxy_base_url, None)
        return

    registration_count = _CURRENT_APP_OPENCLAW_DEFAULT_PATTERN_COUNTS.get(proxy_base_url)
    if registration_count is None:
        return
    if registration_count > 1:
        _CURRENT_APP_OPENCLAW_DEFAULT_PATTERN_COUNTS[proxy_base_url] = registration_count - 1
        return

    _CURRENT_APP_OPENCLAW_DEFAULT_PATTERN_COUNTS.pop(proxy_base_url, None)
    _CURRENT_APP_OPENCLAW_DEFAULT_PATTERNS = [
        (pattern, defaults) for pattern, defaults in _CURRENT_APP_OPENCLAW_DEFAULT_PATTERNS if pattern != proxy_base_url
    ]


def _resolve_current_openclaw_proxy_base_url() -> str:
    env_base_url = os.getenv("OPENCLAW_PROXY_BASE_URL", "").strip()
    if env_base_url:
        return env_base_url.rstrip("/")

    host = os.getenv("OPENCLAW_PROXY_HOST") or "127.0.0.1"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = os.getenv("OPENCLAW_PROXY_PORT") or os.getenv("PORT") or "8000"
    return f"http://{host}:{port}{DEFAULT_OPENCLAW_PROXY_API_PATH}".rstrip("/")


def _has_explicit_openclaw_proxy_base_url() -> bool:
    if os.getenv("OPENCLAW_PROXY_BASE_URL", "").strip():
        return True
    return bool(os.getenv("OPENCLAW_PROXY_HOST") or os.getenv("OPENCLAW_PROXY_PORT") or os.getenv("PORT"))


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


def _normalize_current_app_openclaw_proxy_matcher(
    base_url: str,
) -> tuple[str, str, int, str] | _CurrentAppOpenClawDefaultsPattern:
    parsed = httpx.URL(base_url)
    normalized_path = parsed.path.rstrip("/")
    host = parsed.host or None
    path_has_template = _has_openclaw_proxy_url_template(normalized_path)
    host_has_template = _has_openclaw_proxy_url_template(host or "")
    if parsed.scheme and host and not path_has_template and not host_has_template:
        return _normalize_openclaw_proxy_url(base_url)

    normalized_host_pattern: str | None = None
    if host:
        normalized_host_pattern = _normalize_openclaw_proxy_host(host) if not host_has_template else host.lower()
    port = parsed.port or (443 if parsed.scheme == "https" else 80) if parsed.scheme and host else None
    return _CurrentAppOpenClawDefaultsPattern(
        scheme=parsed.scheme or None,
        host_pattern=normalized_host_pattern,
        port=port,
        path_pattern=normalized_path,
    )


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


def is_loopback_openclaw_proxy_url(base_url: str) -> bool:
    return _is_loopback_openclaw_proxy_url(_normalize_openclaw_proxy_url(base_url))


def _is_loopback_openclaw_proxy_url(base_url: tuple[str, str, int, str]) -> bool:
    scheme, host, _port, path = base_url
    return scheme in {"http", "https"} and host == "loopback" and path == DEFAULT_OPENCLAW_PROXY_API_PATH


def _resolve_current_app_openclaw_defaults(base_url: str) -> _CurrentAppOpenClawDefaults | None:
    exact_match = _get_current_app_openclaw_defaults(base_url)
    if exact_match is not None:
        return exact_match

    normalized_base_url = _normalize_openclaw_proxy_url(base_url)
    for pattern, defaults in _CURRENT_APP_OPENCLAW_DEFAULT_PATTERNS:
        if _matches_current_app_openclaw_defaults_pattern(normalized_base_url, pattern):
            return defaults
    return None


def _matches_current_app_openclaw_defaults_pattern(
    base_url: tuple[str, str, int, str], pattern: _CurrentAppOpenClawDefaultsPattern
) -> bool:
    scheme, host, port, path = base_url
    if pattern.scheme is not None and scheme != pattern.scheme:
        return False
    if pattern.port is not None and port != pattern.port:
        return False
    if pattern.host_pattern is not None and not _matches_openclaw_url_component(
        host, pattern.host_pattern, segment_separator="."
    ):
        return False
    return _matches_openclaw_url_component(path, pattern.path_pattern, segment_separator="/")


def _matches_openclaw_url_component(value: str, pattern: str, *, segment_separator: str) -> bool:
    if not _has_openclaw_proxy_url_template(pattern):
        return value == pattern
    regex = _build_openclaw_url_component_regex(pattern, segment_separator=segment_separator)
    return regex.fullmatch(value) is not None


def _build_openclaw_url_component_regex(pattern: str, *, segment_separator: str) -> re.Pattern[str]:
    placeholder_pattern = re.compile(r"(\{[^{}]+\})")
    wildcard = f"[^{re.escape(segment_separator)}]+"
    regex_parts: list[str] = []
    for part in placeholder_pattern.split(pattern):
        if not part:
            continue
        if part.startswith("{") and part.endswith("}"):
            regex_parts.append(wildcard)
        else:
            regex_parts.append(re.escape(part))
    return re.compile("^" + "".join(regex_parts) + "$")


def _has_openclaw_proxy_url_template(value: str) -> bool:
    return "{" in value and "}" in value


def _resolve_openclaw_default_settings_model_name(model_name: str) -> str:
    if "/" in model_name:
        _, _, bare_model_name = model_name.rpartition("/")
        return bare_model_name or model_name
    return model_name


class _ResponsesModelWithUsageName(Protocol):
    _agency_swarm_usage_model_name: str


class _ResponsesModelWithDefaultSettingsName(Protocol):
    _agency_swarm_default_model_name: str

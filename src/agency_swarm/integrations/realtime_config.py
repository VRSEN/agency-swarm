"""Provider-specific configuration for realtime integrations."""

import os
from collections.abc import Mapping
from typing import Any, Literal, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from agents.realtime.config import (
    RealtimeInputAudioNoiseReductionConfig,
    RealtimeSessionModelSettings,
    RealtimeTurnDetectionConfig,
)

from agency_swarm.agency.helpers import assign_random_agent_voices
from agency_swarm.agent.constants import (
    AGENT_OPENAI_REALTIME_VOICES,
    AGENT_XAI_REALTIME_VOICES,
)
from agency_swarm.realtime.agency import RealtimeAgency

SUPPORTED_REALTIME_PROVIDERS = ("openai", "xai")
XAI_DEFAULT_REALTIME_MODEL = "grok-voice-think-fast-1.0"
XAI_DEFAULT_REALTIME_URL = "wss://api.x.ai/v1/realtime"


def _normalize_provider(provider: str) -> Literal["openai", "xai"]:
    normalized = provider.strip().lower()
    if normalized not in SUPPORTED_REALTIME_PROVIDERS:
        raise ValueError(
            f"Unsupported realtime provider '{provider}'. "
            f"Supported providers: {', '.join(SUPPORTED_REALTIME_PROVIDERS)}."
        )
    return cast(Literal["openai", "xai"], normalized)


def _resolve_model_name(model: str | None, provider: Literal["openai", "xai"]) -> str:
    if model and model.strip():
        return model
    if provider == "xai":
        return XAI_DEFAULT_REALTIME_MODEL
    return "gpt-realtime-2"


def build_model_settings(
    *,
    model: str | None,
    voice: str | None,
    input_audio_format: str | None,
    output_audio_format: str | None,
    turn_detection: dict[str, Any] | None,
    input_audio_noise_reduction: dict[str, Any] | None,
    provider: str = "openai",
) -> RealtimeSessionModelSettings:
    normalized_provider = _normalize_provider(provider)
    settings: RealtimeSessionModelSettings = {"model_name": _resolve_model_name(model, normalized_provider)}
    if voice:
        settings["voice"] = voice
    if input_audio_format:
        settings["input_audio_format"] = input_audio_format
    if output_audio_format:
        settings["output_audio_format"] = output_audio_format
    if turn_detection:
        settings["turn_detection"] = cast(RealtimeTurnDetectionConfig, turn_detection)
    if input_audio_noise_reduction:
        settings["input_audio_noise_reduction"] = cast(
            RealtimeInputAudioNoiseReductionConfig, input_audio_noise_reduction
        )
    return settings


def _resolve_provider_options(
    provider: Literal["openai", "xai"],
    provider_options: Mapping[str, Any] | None,
    *,
    model_name: str | None = None,
) -> dict[str, Any]:
    resolved = dict(provider_options or {})
    if provider == "xai":
        resolved["url"] = str(resolved.get("url") or XAI_DEFAULT_REALTIME_URL)
        if model_name:
            resolved["url"] = _with_xai_model_query(resolved["url"], model_name)
        api_key_env = str(resolved.get("api_key_env") or "XAI_API_KEY")
        resolved.setdefault("api_key_env", api_key_env)
        if "api_key" not in resolved and api_key_env:
            env_value = os.getenv(api_key_env, "").strip()
            if env_value:
                resolved["api_key"] = env_value
    elif provider == "openai":
        api_key_env = str(resolved.get("api_key_env") or "OPENAI_API_KEY")
        resolved.setdefault("api_key_env", api_key_env)
        if "api_key" not in resolved and api_key_env:
            env_value = os.getenv(api_key_env, "").strip()
            if env_value:
                resolved["api_key"] = env_value
    return resolved


def _with_xai_model_query(url: str, model_name: str) -> str:
    parts = urlsplit(url)
    query_items = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "model"]
    query_items.append(("model", model_name))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_items), parts.fragment))


def _provider_voice_pool(provider: Literal["openai", "xai"]) -> tuple[str, ...]:
    if provider == "xai":
        return AGENT_XAI_REALTIME_VOICES
    return AGENT_OPENAI_REALTIME_VOICES


def _resolve_session_voice(
    realtime_agency: RealtimeAgency,
    provider: str,
    voice: str | None,
) -> tuple[Literal["openai", "xai"], str | None]:
    """Resolve the single voice used for a whole realtime session.

    Realtime providers reject a voice change once the model has produced audio, so the voice is
    resolved once here and never updated again. An explicit `voice` wins; otherwise the entry
    agent's `voice` is used. A `voice` set on any other agent never reaches the session.
    """
    normalized_provider = _normalize_provider(provider)
    source = realtime_agency.source
    if source._randomize_agent_voices:
        assign_random_agent_voices(source, _provider_voice_pool(normalized_provider))
        for name, realtime_agent in realtime_agency.agents.items():
            realtime_agent.voice = source.agents[name].voice

    session_voice = voice if voice is not None else realtime_agency.entry_agent.voice
    if session_voice is not None and session_voice not in _provider_voice_pool(normalized_provider):
        raise ValueError(f"Voice '{session_voice}' is not supported by the {normalized_provider} realtime provider.")
    return normalized_provider, session_voice

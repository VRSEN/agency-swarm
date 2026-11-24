"""Unit tests for loop-scoped OpenAI HTTP client patching and wrappers."""

import builtins
from typing import Any

import agents.models.openai_provider as agents_openai_provider
import pytest
from agents.models import _openai_shared
from agents.models.openai_provider import OpenAIProvider

from agency_swarm import Agent
from agency_swarm.agent import openai_client
from agency_swarm.agent.openai_client import _LoopScopedHttpClient


def test_agent_init_patches_sdk_providers_with_loop_scoped_client() -> None:
    """Agent construction installs loop_scoped_http_client on the SDK providers."""
    Agent(name="PatchCheck", instructions="Test")

    assert agents_openai_provider.shared_http_client is openai_client.loop_scoped_http_client
    try:
        from agents.voice.models import openai_model_provider as agents_voice_provider
    except ImportError:
        # voice extra not installed; the guarded patch is skipped by design
        return
    assert agents_voice_provider.shared_http_client is openai_client.loop_scoped_http_client


def test_openai_provider_caches_loop_scoped_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cached SDK provider clients use a loop-scoped HTTP client wrapper."""
    monkeypatch.setattr(_openai_shared, "_default_openai_client", None)
    Agent(name="ProviderCheck", instructions="Test")

    provider = OpenAIProvider(api_key="test-key")
    assert isinstance(provider._get_client()._client, _LoopScopedHttpClient)

    try:
        from agents.voice.models.openai_model_provider import OpenAIVoiceModelProvider
    except ImportError:
        return
    voice_provider = OpenAIVoiceModelProvider(api_key="test-key")
    assert isinstance(voice_provider._get_client()._client, _LoopScopedHttpClient)


def test_install_loop_scoped_http_client_skips_missing_voice_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing optional voice dependencies must not block patching the OpenAI provider."""
    real_import = builtins.__import__

    def _import_without_voice(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "agents.voice.models" or name.startswith("agents.voice."):
            raise ImportError("voice extra missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(openai_client, "_patch_installed", False)
    monkeypatch.setattr(agents_openai_provider, "shared_http_client", lambda: None)
    monkeypatch.setattr(builtins, "__import__", _import_without_voice)

    openai_client.install_loop_scoped_http_client()

    assert agents_openai_provider.shared_http_client is openai_client.loop_scoped_http_client


@pytest.mark.asyncio
async def test_closing_one_loop_scoped_http_client_does_not_close_pool() -> None:
    """Closing one wrapper leaves the per-loop pool and other wrappers usable."""
    first = openai_client.loop_scoped_http_client()
    second = openai_client.loop_scoped_http_client()
    pooled = openai_client.shared_http_client()

    await first.aclose()

    assert first.is_closed
    assert not second.is_closed
    assert not pooled.is_closed

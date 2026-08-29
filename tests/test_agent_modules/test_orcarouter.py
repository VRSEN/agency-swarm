"""OrcaRouter model helper tests."""

import pytest
from agents import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

from agency_swarm.utils.orcarouter import (
    ORCAROUTER_API_KEY_ENV,
    ORCAROUTER_BASE_URL,
    ORCAROUTER_MODEL_PREFIX,
    build_orcarouter_chat_model,
    get_orcarouter_model_name,
    is_orcarouter_model,
    is_orcarouter_model_name,
    strip_orcarouter_prefix,
)


def test_is_orcarouter_model_name() -> None:
    assert is_orcarouter_model_name("orcarouter/openai/gpt-5") is True
    assert is_orcarouter_model_name("openai/gpt-5") is False
    assert is_orcarouter_model_name("orcarouter") is False


def test_strip_orcarouter_prefix() -> None:
    assert strip_orcarouter_prefix("orcarouter/openai/gpt-5") == "openai/gpt-5"
    assert strip_orcarouter_prefix("openai/gpt-5") == "openai/gpt-5"
    assert strip_orcarouter_prefix("orcarouter/auto") == "auto"


def test_constants() -> None:
    assert ORCAROUTER_API_KEY_ENV == "ORCAROUTER_API_KEY"
    assert ORCAROUTER_BASE_URL == "https://api.orcarouter.ai/v1"
    assert ORCAROUTER_MODEL_PREFIX == "orcarouter/"


def test_build_orcarouter_chat_model_with_explicit_client() -> None:
    client = AsyncOpenAI(api_key="sk-orca-test", base_url=ORCAROUTER_BASE_URL)
    model = build_orcarouter_chat_model("orcarouter/openai/gpt-5", openai_client=client)

    assert isinstance(model, OpenAIChatCompletionsModel)
    assert model.model == "openai/gpt-5"
    assert get_orcarouter_model_name(model) == "orcarouter/openai/gpt-5"
    assert model._client is client


def test_build_orcarouter_chat_model_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORCAROUTER_API_KEY", raising=False)

    with pytest.raises(ValueError, match="ORCAROUTER_API_KEY is required"):
        build_orcarouter_chat_model("orcarouter/openai/gpt-5")


def test_build_orcarouter_chat_model_reads_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORCAROUTER_API_KEY", "sk-orca-env")

    model = build_orcarouter_chat_model("orcarouter/openai/gpt-5")

    assert model._client.api_key == "sk-orca-env"
    assert str(model._client.base_url).rstrip("/") == ORCAROUTER_BASE_URL


def test_build_orcarouter_chat_model_strips_usage_prefix() -> None:
    client = AsyncOpenAI(api_key="sk-orca-test", base_url=ORCAROUTER_BASE_URL)
    model = build_orcarouter_chat_model("orcarouter/openai/gpt-5", openai_client=client)

    assert model._agency_swarm_usage_model_name == "orcarouter/openai/gpt-5"
    assert model._agency_swarm_default_model_name == "gpt-5"


def test_is_orcarouter_model() -> None:
    client = AsyncOpenAI(api_key="sk-orca-test", base_url=ORCAROUTER_BASE_URL)
    model = build_orcarouter_chat_model("orcarouter/openai/gpt-5", openai_client=client)
    assert is_orcarouter_model(model) is True
    assert is_orcarouter_model("not-a-model") is False
    assert is_orcarouter_model(OpenAIChatCompletionsModel(model="openai/gpt-5", openai_client=client)) is False


def test_get_orcarouter_model_name_rejects_foreign_model() -> None:
    client = AsyncOpenAI(api_key="sk-openrouter", base_url="https://openrouter.ai/api/v1")
    plain = OpenAIChatCompletionsModel(model="openai/gpt-5", openai_client=client)
    assert get_orcarouter_model_name(plain) is None

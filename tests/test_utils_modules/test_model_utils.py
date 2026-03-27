"""Unit tests for model utility functions."""

from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.models.openai_responses import OpenAIResponsesModel
from openai import AsyncOpenAI

from agency_swarm.utils.model_utils import get_model_name, is_reasoning_model


def test_is_reasoning_model_case_table() -> None:
    """Reasoning detection should stay stable across common model identifiers."""
    client = AsyncOpenAI(api_key="test")
    cases: list[tuple[str | OpenAIResponsesModel | None, bool]] = [
        ("o3", True),
        ("o4-mini", True),
        ("gpt-5.4", True),
        ("gpt-5.4-mini", True),
        (OpenAIResponsesModel(model="openai/gpt-5.4-mini", openai_client=client), True),
        ("gpt-4.1", False),
        (None, False),
        ("", False),
    ]
    for model_name, expected in cases:
        assert is_reasoning_model(model_name) is expected


def test_get_model_name_from_openai_model_objects() -> None:
    """Model-name extraction should work for both Responses and Chat models."""
    client = AsyncOpenAI(api_key="test")
    cases = [
        OpenAIResponsesModel(model="gpt-5.4-mini", openai_client=client),
        OpenAIChatCompletionsModel(model="gpt-5.4-mini", openai_client=client),
    ]
    for model in cases:
        assert get_model_name(model) == "gpt-5.4-mini"

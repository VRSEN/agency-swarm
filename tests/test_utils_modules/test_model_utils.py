"""Unit tests for model utility functions."""

from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.models.openai_responses import OpenAIResponsesModel
from openai import AsyncOpenAI

from agency_swarm.utils.model_utils import get_model_name, is_reasoning_model


def test_is_reasoning_model_with_o_series():
    """O-series models are reasoning models."""
    assert is_reasoning_model("o3") is True
    assert is_reasoning_model("o4-mini") is True


def test_is_reasoning_model_with_gpt5():
    """GPT-5 series models are reasoning models."""
    assert is_reasoning_model("gpt-5") is True
    assert is_reasoning_model("gpt-5-nano") is True
    assert is_reasoning_model("gpt-5-mini") is True


def test_is_reasoning_model_with_gpt4():
    """GPT-4 series models are NOT reasoning models."""
    assert is_reasoning_model("gpt-4o") is False
    assert is_reasoning_model("gpt-4o-mini") is False
    assert is_reasoning_model("gpt-4.1") is False


def test_is_reasoning_model_with_other_models():
    """Other models are not reasoning models."""
    assert is_reasoning_model("gpt-3.5-turbo") is False
    assert is_reasoning_model("claude-3-opus") is False
    assert is_reasoning_model("gemini-pro") is False


def test_is_reasoning_model_with_none():
    """None model name returns False."""
    assert is_reasoning_model(None) is False


def test_is_reasoning_model_with_empty_string():
    """Empty string model name returns False."""
    assert is_reasoning_model("") is False


def test_get_model_name_from_openai_responses_model() -> None:
    """OpenAI Responses models expose their model identifier."""
    client = AsyncOpenAI(api_key="test")
    model = OpenAIResponsesModel(model="gpt-4o", openai_client=client)
    assert get_model_name(model) == "gpt-4o"


def test_get_model_name_from_openai_chat_completions_model() -> None:
    """OpenAI Chat Completions models expose their model identifier."""
    client = AsyncOpenAI(api_key="test")
    model = OpenAIChatCompletionsModel(model="gpt-4.1", openai_client=client)
    assert get_model_name(model) == "gpt-4.1"

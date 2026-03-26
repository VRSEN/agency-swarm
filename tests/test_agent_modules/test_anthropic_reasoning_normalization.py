"""Tests for Anthropic reasoning.summary normalization in apply_framework_defaults."""

import importlib
from typing import Any
from unittest.mock import patch

from agents import Model, ModelSettings
from openai.types.shared.reasoning import Reasoning

from agency_swarm.agent.initialization import apply_framework_defaults


def _make_kwargs(model: str | Model, reasoning: Reasoning | None = None) -> dict[str, Any]:
    settings = ModelSettings(reasoning=reasoning)
    return {"model": model, "model_settings": settings}


class TestAnthropicReasoningNormalization:
    def test_anthropic_strips_reasoning_summary(self):
        """Anthropic models should have reasoning.summary stripped."""
        kwargs = _make_kwargs(
            "anthropic/claude-sonnet-4-20250514",
            Reasoning(effort="low", summary="auto"),
        )

        with patch("agency_swarm.agent.initialization.logger") as mock_logger:
            apply_framework_defaults(kwargs)
            mock_logger.warning.assert_called_once()

        ms: ModelSettings = kwargs["model_settings"]
        assert ms.reasoning is not None
        assert ms.reasoning.effort == "low"
        assert ms.reasoning.summary is None

    def test_anthropic_prefix_detected(self):
        """Models with 'anthropic/' prefix should be detected."""
        kwargs = _make_kwargs(
            "anthropic/claude-3-opus",
            Reasoning(effort="high", summary="auto"),
        )
        apply_framework_defaults(kwargs)
        ms: ModelSettings = kwargs["model_settings"]
        assert ms.reasoning is not None
        assert ms.reasoning.summary is None

    def test_claude_prefix_detected(self):
        """Models starting with 'claude' (no provider prefix) should be detected."""
        kwargs = _make_kwargs(
            "claude-sonnet-4-20250514",
            Reasoning(effort="medium", summary="auto"),
        )
        apply_framework_defaults(kwargs)
        ms: ModelSettings = kwargs["model_settings"]
        assert ms.reasoning is not None
        assert ms.reasoning.summary is None

    def test_openai_preserves_reasoning_summary(self):
        """OpenAI models should keep reasoning.summary intact."""
        kwargs = _make_kwargs(
            "o3",
            Reasoning(effort="low", summary="auto"),
        )
        apply_framework_defaults(kwargs)
        ms: ModelSettings = kwargs["model_settings"]
        assert ms.reasoning is not None
        assert ms.reasoning.summary == "auto"

    def test_openai_gpt5_preserves_reasoning_summary(self):
        """GPT-5 models should keep reasoning.summary intact."""
        kwargs = _make_kwargs(
            "gpt-5",
            Reasoning(effort="high", summary="auto"),
        )
        apply_framework_defaults(kwargs)
        ms: ModelSettings = kwargs["model_settings"]
        assert ms.reasoning is not None
        assert ms.reasoning.summary == "auto"

    def test_no_reasoning_unchanged(self):
        """Models with no reasoning config should pass through unchanged."""
        kwargs = _make_kwargs("anthropic/claude-sonnet-4-20250514", reasoning=None)
        apply_framework_defaults(kwargs)
        ms: ModelSettings = kwargs["model_settings"]
        assert ms.reasoning is None

    def test_litellm_model_object_strips_summary(self):
        """LitellmModel object (not a string) should also have summary stripped."""
        LitellmModel = importlib.import_module("agents.extensions.models.litellm_model").LitellmModel
        kwargs = _make_kwargs(
            LitellmModel(model="anthropic/claude-sonnet-4-20250514"),
            Reasoning(effort="low", summary="auto"),
        )
        apply_framework_defaults(kwargs)
        ms: ModelSettings = kwargs["model_settings"]
        assert ms.reasoning is not None
        assert ms.reasoning.effort == "low"
        assert ms.reasoning.summary is None

    def test_anthropic_no_summary_unchanged(self):
        """Anthropic models with reasoning but no summary should pass through unchanged."""
        kwargs = _make_kwargs(
            "anthropic/claude-sonnet-4-20250514",
            Reasoning(effort="low"),
        )
        apply_framework_defaults(kwargs)
        ms: ModelSettings = kwargs["model_settings"]
        assert ms.reasoning is not None
        assert ms.reasoning.effort == "low"
        assert ms.reasoning.summary is None

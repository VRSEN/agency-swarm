"""
Integration test for Anthropic reasoning.summary normalization with LiteLLM.

Bug: When using Claude models via LiteLLM with reasoning.summary set,
LiteLLM's AnthropicConfig silently drops the dict-form reasoning_effort
because it only handles isinstance(value, str). Agency Swarm works around
this by stripping reasoning.summary for Anthropic models in
apply_framework_defaults(), passing only reasoning.effort.

This test verifies that the summary-stripping workaround correctly normalizes
model_settings at init time and produces a working agent.
"""

import importlib
import os

import pytest
from agents import ModelSettings
from openai.types.shared.reasoning import Reasoning

from agency_swarm import Agency, Agent

litellm = pytest.importorskip("litellm")
LitellmModel = importlib.import_module("agents.extensions.models.litellm_model").LitellmModel

pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY required for Anthropic reasoning test.",
)


class TestLitellmAnthropicReasoning:
    """Verify reasoning.summary is stripped and the resulting agent works."""

    @pytest.mark.asyncio
    async def test_reasoning_summary_stripped_and_agent_works(self) -> None:
        """Summary is stripped at init; agent produces output over 2 streaming turns."""
        litellm.modify_params = True

        agent = Agent(
            name="ReasoningAgent",
            instructions="Reply with one word.",
            model=LitellmModel(model="anthropic/claude-sonnet-4-20250514"),
            model_settings=ModelSettings(
                reasoning=Reasoning(effort="low", summary="auto"),
            ),
        )

        # Verify summary was stripped during init
        assert agent.model_settings.reasoning is not None
        assert agent.model_settings.reasoning.effort == "low"
        assert agent.model_settings.reasoning.summary is None

        agency = Agency(agent, shared_instructions="Test agency")

        # Turn 1
        async for _ in agency.get_response_stream(message="Hi"):
            pass

        messages = agency.thread_manager.get_all_messages()
        assert len(messages) >= 2, f"Expected at least 2 messages after turn 1, got {len(messages)}"

        # Turn 2 — must succeed (no API error from bad history)
        async for _ in agency.get_response_stream(message="Bye"):
            pass

        messages = agency.thread_manager.get_all_messages()
        assert len(messages) >= 4, f"Expected at least 4 messages after turn 2, got {len(messages)}"

    @pytest.mark.asyncio
    async def test_string_model_also_strips_summary(self) -> None:
        """String model identifiers like 'anthropic/...' also have summary stripped."""
        agent = Agent(
            name="StringModelAgent",
            instructions="Reply with one word.",
            model="anthropic/claude-sonnet-4-20250514",
            model_settings=ModelSettings(
                reasoning=Reasoning(effort="low", summary="auto"),
            ),
        )

        assert agent.model_settings.reasoning is not None
        assert agent.model_settings.reasoning.effort == "low"
        assert agent.model_settings.reasoning.summary is None

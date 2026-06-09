from typing import Any, cast

import pytest
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.completion_usage import CompletionUsage

from agency_swarm import Agent, Runner, set_tracing_disabled
from agency_swarm.utils.openrouter import build_openrouter_chat_model


class _Completions:
    async def create(self, **_kwargs: Any) -> ChatCompletion:
        message = ChatCompletionMessage(role="assistant", content="final answer")
        message.reasoning = "provider reasoning"
        message.reasoning_details = [
            {
                "type": "reasoning.text",
                "text": "provider detail",
                "signature": "reasoning-signature",
            }
        ]
        return ChatCompletion(
            id="chatcmpl_test",
            choices=[
                Choice(
                    finish_reason="stop",
                    index=0,
                    logprobs=None,
                    message=message,
                )
            ],
            created=0,
            model="openai/gpt-5",
            object="chat.completion",
            usage=CompletionUsage(completion_tokens=2, prompt_tokens=1, total_tokens=3),
        )


class _Chat:
    def __init__(self) -> None:
        self.completions = _Completions()


class _Client:
    def __init__(self) -> None:
        self.chat = _Chat()
        self.base_url = "https://openrouter.ai/api/v1"


@pytest.mark.asyncio
async def test_openrouter_runner_surfaces_reasoning_metadata() -> None:
    """Runner output should include OpenRouter reasoning from OpenAI-compatible chat."""
    set_tracing_disabled(True)
    model = build_openrouter_chat_model(
        "openrouter/openai/gpt-5",
        openai_client=cast(Any, _Client()),
    )
    agent = Agent(name="OpenRouterAgent", instructions="Reply briefly.", model=model)

    result = await Runner.run(agent, "hello")

    items = result.raw_responses[0].output
    assert [item.type for item in items] == ["reasoning", "message"]

    reasoning = items[0]
    assert reasoning.summary[0].text == "provider reasoning"
    assert reasoning.content[0].text == "provider detail"
    assert reasoning.encrypted_content == "reasoning-signature"
    assert result.final_output == "final answer"

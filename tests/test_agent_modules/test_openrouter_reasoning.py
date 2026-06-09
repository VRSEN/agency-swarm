import asyncio
from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
from agents.stream_events import RawResponsesStreamEvent
from openai.types.chat import ChatCompletion, ChatCompletionChunk, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice, ChoiceDelta
from openai.types.completion_usage import CompletionUsage

from agency_swarm import Agent, Runner, set_tracing_disabled
from agency_swarm.utils.openrouter import (
    _OPENROUTER_REPLAY_DETAILS,
    _details_from_reasoning_item,
    _normalize_openrouter_reasoning_stream,
    build_openrouter_chat_model,
)


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


class _DetailsCompletions:
    async def create(self, **_kwargs: Any) -> ChatCompletion:
        message = ChatCompletionMessage(role="assistant", content="final answer")
        message.reasoning_details = _reasoning_details()
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
            model="anthropic/claude-sonnet-4.5",
            object="chat.completion",
            usage=CompletionUsage(completion_tokens=2, prompt_tokens=1, total_tokens=3),
        )


class _DetailsChat:
    def __init__(self) -> None:
        self.completions = _DetailsCompletions()


class _DetailsClient:
    def __init__(self) -> None:
        self.chat = _DetailsChat()
        self.base_url = "https://openrouter.ai/api/v1"


class _StreamCompletions:
    async def create(self, **kwargs: Any) -> ChatCompletion | AsyncIterator[ChatCompletionChunk]:
        if kwargs.get("stream"):
            return _stream_chunks()
        raise AssertionError("streaming test must request stream=True")


class _StreamChat:
    def __init__(self) -> None:
        self.completions = _StreamCompletions()


class _StreamClient:
    def __init__(self) -> None:
        self.chat = _StreamChat()
        self.base_url = "https://openrouter.ai/api/v1"


class _EncryptedCompletions:
    async def create(self, **_kwargs: Any) -> ChatCompletion:
        message = ChatCompletionMessage(role="assistant", content="final answer")
        message.reasoning_details = [_encrypted_reasoning_detail()]
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
            model="anthropic/claude-sonnet-4.5",
            object="chat.completion",
            usage=CompletionUsage(completion_tokens=2, prompt_tokens=1, total_tokens=3),
        )


class _EncryptedChat:
    def __init__(self) -> None:
        self.completions = _EncryptedCompletions()


class _EncryptedClient:
    def __init__(self) -> None:
        self.chat = _EncryptedChat()
        self.base_url = "https://openrouter.ai/api/v1"


class _EncryptedStreamCompletions:
    async def create(self, **kwargs: Any) -> ChatCompletion | AsyncIterator[ChatCompletionChunk]:
        if kwargs.get("stream"):
            return _encrypted_stream_chunks()
        raise AssertionError("streaming test must request stream=True")


class _EncryptedStreamChat:
    def __init__(self) -> None:
        self.completions = _EncryptedStreamCompletions()


class _EncryptedStreamClient:
    def __init__(self) -> None:
        self.chat = _EncryptedStreamChat()
        self.base_url = "https://openrouter.ai/api/v1"


class _TextOnlyStreamCompletions:
    async def create(self, **kwargs: Any) -> ChatCompletion | AsyncIterator[ChatCompletionChunk]:
        if kwargs.get("stream"):
            return _text_only_stream_chunks()
        raise AssertionError("streaming test must request stream=True")


class _TextOnlyStreamChat:
    def __init__(self) -> None:
        self.completions = _TextOnlyStreamCompletions()


class _TextOnlyStreamClient:
    def __init__(self) -> None:
        self.chat = _TextOnlyStreamChat()
        self.base_url = "https://openrouter.ai/api/v1"


class _ReplayCompletions:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> ChatCompletion:
        self.requests.append(kwargs)
        message = ChatCompletionMessage(role="assistant", content=f"turn {len(self.requests)}")
        if len(self.requests) == 1:
            message.reasoning_details = _reasoning_details()
        return ChatCompletion(
            id=f"chatcmpl_test_{len(self.requests)}",
            choices=[
                Choice(
                    finish_reason="stop",
                    index=0,
                    logprobs=None,
                    message=message,
                )
            ],
            created=0,
            model="anthropic/claude-sonnet-4.5",
            object="chat.completion",
            usage=CompletionUsage(completion_tokens=2, prompt_tokens=1, total_tokens=3),
        )


class _ReplayChat:
    def __init__(self) -> None:
        self.completions = _ReplayCompletions()


class _ReplayClient:
    def __init__(self) -> None:
        self.chat = _ReplayChat()
        self.base_url = "https://openrouter.ai/api/v1"


class _MixedChoiceCompletions:
    async def create(self, **_kwargs: Any) -> ChatCompletion:
        first = ChatCompletionMessage(role="assistant", content="first answer")
        first.reasoning = "first summary"
        second = ChatCompletionMessage(role="assistant", content="second answer")
        second.reasoning_details = [
            {"type": "reasoning.text", "text": "second detail", "signature": "second-signature"}
        ]
        return ChatCompletion(
            id="chatcmpl_mixed",
            choices=[
                Choice(finish_reason="stop", index=0, logprobs=None, message=first),
                Choice(finish_reason="stop", index=1, logprobs=None, message=second),
            ],
            created=0,
            model="anthropic/claude-sonnet-4.5",
            object="chat.completion",
            usage=CompletionUsage(completion_tokens=2, prompt_tokens=1, total_tokens=3),
        )


class _MixedChoiceChat:
    def __init__(self) -> None:
        self.completions = _MixedChoiceCompletions()


class _MixedChoiceClient:
    def __init__(self) -> None:
        self.chat = _MixedChoiceChat()
        self.base_url = "https://openrouter.ai/api/v1"


class _ReasoningContentCompletions:
    async def create(self, **_kwargs: Any) -> ChatCompletion:
        message = ChatCompletionMessage(role="assistant", content="final answer")
        message.reasoning_content = "content reasoning"
        return ChatCompletion(
            id="chatcmpl_reasoning_content",
            choices=[Choice(finish_reason="stop", index=0, logprobs=None, message=message)],
            created=0,
            model="anthropic/claude-sonnet-4.5",
            object="chat.completion",
            usage=CompletionUsage(completion_tokens=2, prompt_tokens=1, total_tokens=3),
        )


class _ReasoningContentChat:
    def __init__(self) -> None:
        self.completions = _ReasoningContentCompletions()


class _ReasoningContentClient:
    def __init__(self) -> None:
        self.chat = _ReasoningContentChat()
        self.base_url = "https://openrouter.ai/api/v1"


class _ThinkingBlocksCompletions:
    async def create(self, **_kwargs: Any) -> ChatCompletion:
        message = ChatCompletionMessage(role="assistant", content="final answer")
        message.thinking_blocks = [{"thinking": "block reasoning", "signature": "block-signature"}]
        return ChatCompletion(
            id="chatcmpl_thinking_blocks",
            choices=[Choice(finish_reason="stop", index=0, logprobs=None, message=message)],
            created=0,
            model="anthropic/claude-sonnet-4.5",
            object="chat.completion",
            usage=CompletionUsage(completion_tokens=2, prompt_tokens=1, total_tokens=3),
        )


class _ThinkingBlocksChat:
    def __init__(self) -> None:
        self.completions = _ThinkingBlocksCompletions()


class _ThinkingBlocksClient:
    def __init__(self) -> None:
        self.chat = _ThinkingBlocksChat()
        self.base_url = "https://openrouter.ai/api/v1"


class _SplitReasoningCompletions:
    async def create(self, **_kwargs: Any) -> ChatCompletion:
        message = ChatCompletionMessage(role="assistant", content="final answer")
        message.reasoning_details = [
            {"type": "reasoning.summary", "summary": "first summary"},
            {"type": "reasoning.summary", "summary": "second summary"},
            {"type": "reasoning.text", "text": "first text"},
            {"type": "reasoning.text", "text": "second text"},
        ]
        return ChatCompletion(
            id="chatcmpl_split_reasoning",
            choices=[Choice(finish_reason="stop", index=0, logprobs=None, message=message)],
            created=0,
            model="anthropic/claude-sonnet-4.5",
            object="chat.completion",
            usage=CompletionUsage(completion_tokens=2, prompt_tokens=1, total_tokens=3),
        )


class _SplitReasoningChat:
    def __init__(self) -> None:
        self.completions = _SplitReasoningCompletions()


class _SplitReasoningClient:
    def __init__(self) -> None:
        self.chat = _SplitReasoningChat()
        self.base_url = "https://openrouter.ai/api/v1"


class _MutationCompletions:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] | None = None

    async def create(self, **kwargs: Any) -> ChatCompletion:
        self.messages = kwargs["messages"]
        return ChatCompletion(
            id="chatcmpl_mutation",
            choices=[
                Choice(
                    finish_reason="stop",
                    index=0,
                    logprobs=None,
                    message=ChatCompletionMessage(role="assistant", content="ok"),
                )
            ],
            created=0,
            model="anthropic/claude-sonnet-4.5",
            object="chat.completion",
        )


class _MutationChat:
    def __init__(self) -> None:
        self.completions = _MutationCompletions()


class _MutationClient:
    def __init__(self) -> None:
        self.chat = _MutationChat()
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


@pytest.mark.asyncio
async def test_openrouter_runner_preserves_documented_reasoning_details() -> None:
    """Documented summary, encrypted, and text details should survive conversion."""
    set_tracing_disabled(True)
    model = build_openrouter_chat_model(
        "openrouter/anthropic/claude-sonnet-4.5",
        openai_client=cast(Any, _DetailsClient()),
    )
    agent = Agent(name="OpenRouterAgent", instructions="Reply briefly.", model=model)

    result = await Runner.run(agent, "hello")

    reasoning = result.raw_responses[0].output[0]
    assert reasoning.type == "reasoning"
    assert reasoning.summary[0].text == "documented summary"
    assert reasoning.content[0].text == "documented text"
    assert reasoning.encrypted_content == "encrypted-data\ntext-signature"
    assert result.final_output == "final answer"


@pytest.mark.asyncio
async def test_openrouter_streamed_reasoning_details_surface_through_runner() -> None:
    """Streaming delta.reasoning_details should reach the SDK reasoning events."""
    set_tracing_disabled(True)
    model = build_openrouter_chat_model(
        "openrouter/anthropic/claude-sonnet-4.5",
        openai_client=cast(Any, _StreamClient()),
    )
    agent = Agent(name="OpenRouterAgent", instructions="Reply briefly.", model=model)

    result = Runner.run_streamed(agent, "hello")
    events = [event async for event in result.stream_events()]
    raw = [event.data for event in events if isinstance(event, RawResponsesStreamEvent)]

    summary_deltas = [event.delta for event in raw if event.type == "response.reasoning_summary_text.delta"]
    text_deltas = [event.delta for event in raw if event.type == "response.reasoning_text.delta"]
    completed = next(event.response for event in raw if event.type == "response.completed")
    reasoning = completed.output[0]

    assert summary_deltas == ["documented summary"]
    assert text_deltas == ["documented text"]
    assert reasoning.type == "reasoning"
    assert reasoning.summary[0].text == "documented summary"
    assert reasoning.content[0].text == "documented text"
    assert reasoning.encrypted_content == "encrypted-data\ntext-signature"


@pytest.mark.asyncio
async def test_openrouter_runner_preserves_encrypted_only_reasoning_details() -> None:
    """Encrypted-only details should still create a reasoning item."""
    set_tracing_disabled(True)
    model = build_openrouter_chat_model(
        "openrouter/anthropic/claude-sonnet-4.5",
        openai_client=cast(Any, _EncryptedClient()),
    )
    agent = Agent(name="OpenRouterAgent", instructions="Reply briefly.", model=model)

    result = await Runner.run(agent, "hello")

    reasoning = result.raw_responses[0].output[0]
    assert reasoning.type == "reasoning"
    assert reasoning.summary[0].text == "[REDACTED]"
    assert reasoning.content == []
    assert reasoning.encrypted_content == "encrypted-data"
    assert result.final_output == "final answer"


@pytest.mark.asyncio
async def test_openrouter_streamed_encrypted_only_reasoning_details_surface_through_runner() -> None:
    """Streaming encrypted-only details should still create a reasoning item."""
    set_tracing_disabled(True)
    model = build_openrouter_chat_model(
        "openrouter/anthropic/claude-sonnet-4.5",
        openai_client=cast(Any, _EncryptedStreamClient()),
    )
    agent = Agent(name="OpenRouterAgent", instructions="Reply briefly.", model=model)

    result = Runner.run_streamed(agent, "hello")
    events = [event async for event in result.stream_events()]
    raw = [event.data for event in events if isinstance(event, RawResponsesStreamEvent)]

    summary_deltas = [event.delta for event in raw if event.type == "response.reasoning_summary_text.delta"]
    completed = next(event.response for event in raw if event.type == "response.completed")
    reasoning = completed.output[0]

    assert summary_deltas == ["[REDACTED]"]
    assert reasoning.type == "reasoning"
    assert reasoning.summary[0].text == "[REDACTED]"
    assert reasoning.content is None
    assert reasoning.encrypted_content == "encrypted-data"


@pytest.mark.asyncio
async def test_openrouter_replays_reasoning_details_on_next_request() -> None:
    """A second turn should pass prior OpenRouter reasoning details back."""
    set_tracing_disabled(True)
    client = _ReplayClient()
    model = build_openrouter_chat_model(
        "openrouter/anthropic/claude-sonnet-4.5",
        openai_client=cast(Any, client),
    )
    agent = Agent(name="OpenRouterAgent", instructions="Reply briefly.", model=model)

    first = await Runner.run(agent, "hello")
    await Runner.run(
        agent,
        [
            *first.to_input_list(),
            {
                "role": "user",
                "content": "again",
            },
        ],
    )

    messages = client.chat.completions.requests[1]["messages"]
    assistant = next(message for message in messages if message["role"] == "assistant")
    assert assistant["reasoning_details"] == _reasoning_details()


@pytest.mark.asyncio
async def test_openrouter_replay_details_can_be_disabled() -> None:
    """A caller-provided replay policy should be able to block OpenRouter detail replay."""
    set_tracing_disabled(True)
    client = _ReplayClient()
    model = build_openrouter_chat_model(
        "openrouter/anthropic/claude-sonnet-4.5",
        openai_client=cast(Any, client),
        should_replay_reasoning_content=lambda _context: False,
    )
    agent = Agent(name="OpenRouterAgent", instructions="Reply briefly.", model=model)

    first = await Runner.run(agent, "hello")
    await Runner.run(agent, [*first.to_input_list(), {"role": "user", "content": "again"}])

    messages = client.chat.completions.requests[1]["messages"]
    assistant = next(message for message in messages if message["role"] == "assistant")
    assert "reasoning_details" not in assistant


@pytest.mark.asyncio
async def test_openrouter_runner_surfaces_non_stream_reasoning_content() -> None:
    """OpenRouter sync responses can provide reasoning_content without details."""
    set_tracing_disabled(True)
    model = build_openrouter_chat_model(
        "openrouter/anthropic/claude-sonnet-4.5",
        openai_client=cast(Any, _ReasoningContentClient()),
    )
    agent = Agent(name="OpenRouterAgent", instructions="Reply briefly.", model=model)

    result = await Runner.run(agent, "hello")

    reasoning = result.raw_responses[0].output[0]
    assert reasoning.summary[0].text == "content reasoning"


@pytest.mark.asyncio
async def test_openrouter_runner_surfaces_non_stream_thinking_blocks() -> None:
    """OpenRouter sync responses can provide thinking_blocks without details."""
    set_tracing_disabled(True)
    model = build_openrouter_chat_model(
        "openrouter/anthropic/claude-sonnet-4.5",
        openai_client=cast(Any, _ThinkingBlocksClient()),
    )
    agent = Agent(name="OpenRouterAgent", instructions="Reply briefly.", model=model)

    result = await Runner.run(agent, "hello")

    reasoning = result.raw_responses[0].output[0]
    assert reasoning.summary[0].text == "block reasoning"
    assert reasoning.encrypted_content == "block-signature"


@pytest.mark.asyncio
async def test_openrouter_details_from_second_choice_do_not_attach_to_first_choice() -> None:
    """OpenRouter reasoning does not silently drop later chat choices."""
    set_tracing_disabled(True)
    model = build_openrouter_chat_model(
        "openrouter/anthropic/claude-sonnet-4.5",
        openai_client=cast(Any, _MixedChoiceClient()),
    )
    agent = Agent(name="OpenRouterAgent", instructions="Reply briefly.", model=model)

    with pytest.raises(ValueError, match="single-choice"):
        await Runner.run(agent, "hello")


@pytest.mark.asyncio
async def test_openrouter_replay_details_do_not_mutate_caller_messages() -> None:
    """Replay enrichment should copy request messages before adding OpenRouter fields."""
    client = _MutationClient()
    model = build_openrouter_chat_model(
        "openrouter/anthropic/claude-sonnet-4.5",
        openai_client=cast(Any, client),
    )
    messages = [{"role": "assistant", "content": "previous", "reasoning_content": "documented summary"}]
    token = _OPENROUTER_REPLAY_DETAILS.set([_reasoning_details()])
    try:
        await model._get_client().chat.completions.create(messages=messages)
    finally:
        _OPENROUTER_REPLAY_DETAILS.reset(token)

    assert "reasoning_details" not in messages[0]
    assert client.chat.completions.messages is not messages
    assert client.chat.completions.messages is not None
    assert client.chat.completions.messages[0]["reasoning_details"] == _reasoning_details()


@pytest.mark.asyncio
async def test_openrouter_replay_details_respect_sdk_replay_policy() -> None:
    """Replay enrichment should not add details when the SDK did not mark replay."""
    client = _MutationClient()
    model = build_openrouter_chat_model(
        "openrouter/anthropic/claude-sonnet-4.5",
        openai_client=cast(Any, client),
    )
    messages = [{"role": "assistant", "content": "previous"}]
    token = _OPENROUTER_REPLAY_DETAILS.set([_reasoning_details()])
    try:
        await model._get_client().chat.completions.create(messages=messages)
    finally:
        _OPENROUTER_REPLAY_DETAILS.reset(token)

    assert client.chat.completions.messages is not None
    assert "reasoning_details" not in client.chat.completions.messages[0]


@pytest.mark.asyncio
async def test_openrouter_replay_details_attach_to_latest_assistant_message() -> None:
    """Replay enrichment should not attach current reasoning to older assistant turns."""
    client = _MutationClient()
    model = build_openrouter_chat_model(
        "openrouter/anthropic/claude-sonnet-4.5",
        openai_client=cast(Any, client),
    )
    messages = [
        {"role": "assistant", "content": "older"},
        {"role": "user", "content": "next"},
        {"role": "assistant", "content": "current", "reasoning_content": "documented summary"},
    ]
    token = _OPENROUTER_REPLAY_DETAILS.set([_reasoning_details()])
    try:
        await model._get_client().chat.completions.create(messages=messages)
    finally:
        _OPENROUTER_REPLAY_DETAILS.reset(token)

    assert client.chat.completions.messages is not None
    assert "reasoning_details" not in client.chat.completions.messages[0]
    assert client.chat.completions.messages[2]["reasoning_details"] == _reasoning_details()


def test_openrouter_replay_fallback_drops_redaction_placeholder() -> None:
    """A local display placeholder should not be sent back as provider reasoning."""
    details = _details_from_reasoning_item(
        {
            "type": "reasoning",
            "summary": [{"text": "[REDACTED]"}],
            "content": [{"text": "real text"}],
            "encrypted_content": "encrypted-data\ntext-signature",
        }
    )

    assert details == [
        {"type": "reasoning.encrypted", "data": "encrypted-data"},
        {"type": "reasoning.text", "text": "real text", "signature": "text-signature"},
    ]


@pytest.mark.asyncio
async def test_openrouter_reasoning_fragments_preserve_boundaries() -> None:
    """Multiple reasoning fragments should keep readable separators."""
    set_tracing_disabled(True)
    model = build_openrouter_chat_model(
        "openrouter/anthropic/claude-sonnet-4.5",
        openai_client=cast(Any, _SplitReasoningClient()),
    )
    agent = Agent(name="OpenRouterAgent", instructions="Reply briefly.", model=model)

    result = await Runner.run(agent, "hello")

    reasoning = result.raw_responses[0].output[0]
    assert reasoning.summary[0].text == "first summary\nsecond summary"
    assert [content.text for content in reasoning.content] == ["first text", "second text"]


@pytest.mark.asyncio
async def test_openrouter_streamed_reasoning_details_stay_separate_by_choice() -> None:
    """Multi-choice streams should not silently mix reasoning metadata across choices."""
    stream = _normalize_openrouter_reasoning_stream(_multi_choice_stream_chunks())

    with pytest.raises(ValueError, match="single-choice"):
        _ = [chunk async for chunk in stream]


@pytest.mark.asyncio
async def test_openrouter_stream_without_details_keeps_litellm_reasoning_fallback() -> None:
    """OpenRouter should not disable shared reasoning fallback without reasoning_details."""
    delta = ChoiceDelta()
    delta.thinking_blocks = [{"thinking": "fallback reasoning", "signature": "fallback-signature"}]
    stream = _normalize_openrouter_reasoning_stream(_single_chunk_stream(_chunk("chunk_fallback", delta)))

    chunks = [chunk async for chunk in stream]

    normalized = chunks[0].choices[0].delta
    assert not getattr(normalized, "_agency_swarm_skip_reasoning_content_copy", False)
    assert normalized.thinking_blocks == [
        {"thinking": "fallback reasoning", "signature": "fallback-signature"}
    ]


@pytest.mark.asyncio
async def test_openrouter_streamed_text_only_reasoning_details_surface_through_runner() -> None:
    """Streaming text-only reasoning_details should still create reasoning output."""
    set_tracing_disabled(True)
    model = build_openrouter_chat_model(
        "openrouter/anthropic/claude-sonnet-4.5",
        openai_client=cast(Any, _TextOnlyStreamClient()),
    )
    agent = Agent(name="OpenRouterAgent", instructions="Reply briefly.", model=model)

    result = Runner.run_streamed(agent, "hello")
    events = [event async for event in result.stream_events()]
    raw = [event.data for event in events if isinstance(event, RawResponsesStreamEvent)]

    summary_deltas = [event.delta for event in raw if event.type == "response.reasoning_summary_text.delta"]
    text_deltas = [event.delta for event in raw if event.type == "response.reasoning_text.delta"]
    completed = next(event.response for event in raw if event.type == "response.completed")
    reasoning = completed.output[0]

    assert summary_deltas == ["text-only detail"]
    assert text_deltas == ["text-only detail"]
    assert reasoning.type == "reasoning"
    assert reasoning.summary[0].text == "text-only detail"
    assert reasoning.content[0].text == "text-only detail"


@pytest.mark.asyncio
async def test_openrouter_parallel_runs_keep_provider_data_separate() -> None:
    """Overlapping runs on one model should attach their own reasoning_details."""
    set_tracing_disabled(True)
    client = _ParallelClient()
    model = build_openrouter_chat_model(
        "openrouter/anthropic/claude-sonnet-4.5",
        openai_client=cast(Any, client),
    )
    agent = Agent(name="OpenRouterAgent", instructions="Reply briefly.", model=model)

    first, second = await asyncio.gather(
        Runner.run(agent, "first"),
        Runner.run(agent, "second"),
    )

    assert first.raw_responses[0].output[0].provider_data["openrouter_reasoning_details"] == [
        {"type": "reasoning.text", "text": "first detail", "signature": "first-signature"}
    ]
    assert second.raw_responses[0].output[0].provider_data["openrouter_reasoning_details"] == [
        {"type": "reasoning.text", "text": "second detail", "signature": "second-signature"}
    ]


def _reasoning_details() -> list[dict[str, object]]:
    return [
        {
            "type": "reasoning.summary",
            "summary": "documented summary",
            "id": "reasoning-summary-1",
            "format": "anthropic-claude-v1",
            "index": 0,
            "unknown_field": "summary-extra",
        },
        {
            "type": "reasoning.encrypted",
            "data": "encrypted-data",
            "id": "reasoning-encrypted-1",
            "format": "anthropic-claude-v1",
            "index": 1,
            "unknown_field": "encrypted-extra",
        },
        {
            "type": "reasoning.text",
            "text": "documented text",
            "signature": "text-signature",
            "id": "reasoning-text-1",
            "format": "anthropic-claude-v1",
            "index": 2,
            "unknown_field": "text-extra",
        },
    ]


def _encrypted_reasoning_detail() -> dict[str, object]:
    return {
        "type": "reasoning.encrypted",
        "data": "encrypted-data",
        "id": "reasoning-encrypted-1",
        "format": "anthropic-claude-v1",
        "index": 0,
    }


async def _stream_chunks() -> AsyncIterator[ChatCompletionChunk]:
    for index, detail in enumerate(_reasoning_details()):
        delta = ChoiceDelta()
        delta.reasoning_details = [detail]
        yield _chunk(f"chunk_{index}", delta)
    yield _chunk("chunk_content", ChoiceDelta(content="final answer"))


async def _encrypted_stream_chunks() -> AsyncIterator[ChatCompletionChunk]:
    delta = ChoiceDelta()
    delta.reasoning_details = [_encrypted_reasoning_detail()]
    yield _chunk("chunk_encrypted", delta)
    yield _chunk("chunk_content", ChoiceDelta(content="final answer"))


async def _text_only_stream_chunks() -> AsyncIterator[ChatCompletionChunk]:
    delta = ChoiceDelta()
    delta.reasoning_details = [{"type": "reasoning.text", "text": "text-only detail"}]
    yield _chunk("chunk_text_only", delta)
    yield _chunk("chunk_content", ChoiceDelta(content="final answer"))


async def _multi_choice_stream_chunks() -> AsyncIterator[ChatCompletionChunk]:
    first = ChoiceDelta()
    first.reasoning_details = [
        {"type": "reasoning.summary", "summary": "choice zero"},
        {"type": "reasoning.text", "text": "zero text", "signature": "zero-signature"},
    ]
    second = ChoiceDelta()
    second.reasoning_details = [
        {"type": "reasoning.summary", "summary": "choice one"},
        {"type": "reasoning.text", "text": "one text", "signature": "one-signature"},
    ]
    yield ChatCompletionChunk(
        id="chunk_multi",
        choices=[
            ChunkChoice(delta=first, finish_reason=None, index=0, logprobs=None),
            ChunkChoice(delta=second, finish_reason=None, index=1, logprobs=None),
        ],
        created=0,
        model="anthropic/claude-sonnet-4.5",
        object="chat.completion.chunk",
    )


async def _single_chunk_stream(chunk: ChatCompletionChunk) -> AsyncIterator[ChatCompletionChunk]:
    yield chunk


def _chunk(chunk_id: str, delta: ChoiceDelta) -> ChatCompletionChunk:
    return ChatCompletionChunk(
        id=chunk_id,
        choices=[
            ChunkChoice(
                delta=delta,
                finish_reason=None,
                index=0,
                logprobs=None,
            )
        ],
        created=0,
        model="anthropic/claude-sonnet-4.5",
        object="chat.completion.chunk",
    )


class _ParallelCompletions:
    async def create(self, **kwargs: Any) -> ChatCompletion:
        text = _last_user_text(kwargs["messages"])
        await asyncio.sleep(0)
        message = ChatCompletionMessage(role="assistant", content=f"{text} answer")
        message.reasoning_details = [
            {
                "type": "reasoning.text",
                "text": f"{text} detail",
                "signature": f"{text}-signature",
            }
        ]
        return ChatCompletion(
            id=f"chatcmpl_{text}",
            choices=[
                Choice(
                    finish_reason="stop",
                    index=0,
                    logprobs=None,
                    message=message,
                )
            ],
            created=0,
            model="anthropic/claude-sonnet-4.5",
            object="chat.completion",
            usage=CompletionUsage(completion_tokens=2, prompt_tokens=1, total_tokens=3),
        )


class _ParallelChat:
    def __init__(self) -> None:
        self.completions = _ParallelCompletions()


class _ParallelClient:
    def __init__(self) -> None:
        self.chat = _ParallelChat()
        self.base_url = "https://openrouter.ai/api/v1"


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text = next((item.get("text") for item in content if isinstance(item, dict)), None)
            if isinstance(text, str):
                return text
    raise AssertionError("missing user message")

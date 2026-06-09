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
    messages = [{"role": "assistant", "content": "previous"}]
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
        {"role": "assistant", "content": "current"},
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
async def test_openrouter_streamed_reasoning_details_stay_separate_by_choice() -> None:
    """Multi-choice streams should not silently mix reasoning metadata across choices."""
    stream = _normalize_openrouter_reasoning_stream(_multi_choice_stream_chunks())

    with pytest.raises(ValueError, match="single-choice"):
        _ = [chunk async for chunk in stream]


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

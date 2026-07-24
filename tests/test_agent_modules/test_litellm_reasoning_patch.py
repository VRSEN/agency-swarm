import importlib
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_litellm_thinking_blocks_emit_reasoning_events() -> None:
    """LiteLLM thinking_blocks should be visible as reasoning stream deltas."""
    pytest.importorskip("agents.extensions.models.litellm_model")

    patch = importlib.import_module("agency_swarm.streaming.litellm_reasoning")
    patch.patch_litellm_thinking_blocks()
    from agents.extensions.models.litellm_model import ChatCmplStreamHandler
    from openai.types.responses import Response

    async def stream():
        yield SimpleNamespace(
            id="chatcmpl_1",
            model="anthropic/claude-sonnet-4",
            usage=None,
            choices=[
                SimpleNamespace(
                    index=0,
                    logprobs=None,
                    delta=SimpleNamespace(
                        content=None,
                        refusal=None,
                        tool_calls=None,
                        thinking_blocks=[{"thinking": "Check the tool result."}],
                    ),
                )
            ],
        )

    response = Response(
        id="resp_1",
        created_at=0.0,
        model="anthropic/claude-sonnet-4",
        object="response",
        output=[],
        parallel_tool_calls=False,
        tool_choice="auto",
        tools=[],
    )

    events = [
        event
        async for event in ChatCmplStreamHandler.handle_stream(
            response,
            stream(),
            "anthropic/claude-sonnet-4",
        )
    ]

    reasoning_deltas = [
        event.delta for event in events if getattr(event, "type", "") == "response.reasoning_summary_text.delta"
    ]
    assert reasoning_deltas == ["Check the tool result."]


@pytest.mark.asyncio
async def test_litellm_model_extra_reasoning_content_emits_reasoning_events() -> None:
    """Gemini can expose reasoning fields through provider/model extras instead of attributes."""
    pytest.importorskip("agents.extensions.models.litellm_model")

    patch = importlib.import_module("agency_swarm.streaming.litellm_reasoning")
    patch.patch_litellm_thinking_blocks()
    from agents.extensions.models.litellm_model import ChatCmplStreamHandler
    from openai.types.responses import Response

    async def stream():
        yield SimpleNamespace(
            id="chatcmpl_1",
            model="gemini/gemini-2.5-pro",
            usage=None,
            choices=[
                SimpleNamespace(
                    index=0,
                    logprobs=None,
                    delta=SimpleNamespace(
                        content=None,
                        refusal=None,
                        tool_calls=None,
                        model_extra={"reasoning_content": "Check Gemini thought."},
                    ),
                )
            ],
        )

    response = Response(
        id="resp_1",
        created_at=0.0,
        model="gemini/gemini-2.5-pro",
        object="response",
        output=[],
        parallel_tool_calls=False,
        tool_choice="auto",
        tools=[],
    )

    events = [
        event
        async for event in ChatCmplStreamHandler.handle_stream(
            response,
            stream(),
            "gemini/gemini-2.5-pro",
        )
    ]

    reasoning_deltas = [
        event.delta for event in events if getattr(event, "type", "") == "response.reasoning_summary_text.delta"
    ]
    assert reasoning_deltas == ["Check Gemini thought."]


@pytest.mark.asyncio
async def test_litellm_reasoning_field_emits_reasoning_events() -> None:
    """LiteLLM reasoning fields should be visible as reasoning stream deltas."""
    pytest.importorskip("agents.extensions.models.litellm_model")

    patch = importlib.import_module("agency_swarm.streaming.litellm_reasoning")
    patch.patch_litellm_thinking_blocks()
    from agents.extensions.models.litellm_model import ChatCmplStreamHandler
    from openai.types.responses import Response

    async def stream():
        yield SimpleNamespace(
            id="chatcmpl_1",
            model="xai/grok-code-fast",
            usage=None,
            choices=[
                SimpleNamespace(
                    index=0,
                    logprobs=None,
                    delta=SimpleNamespace(
                        content=None,
                        refusal=None,
                        tool_calls=None,
                        reasoning="Check xAI thought.",
                    ),
                )
            ],
        )

    response = Response(
        id="resp_1",
        created_at=0.0,
        model="xai/grok-code-fast",
        object="response",
        output=[],
        parallel_tool_calls=False,
        tool_choice="auto",
        tools=[],
    )

    events = [
        event
        async for event in ChatCmplStreamHandler.handle_stream(
            response,
            stream(),
            "xai/grok-code-fast",
        )
    ]

    reasoning_deltas = [
        event.delta for event in events if getattr(event, "type", "") == "response.reasoning_summary_text.delta"
    ]
    assert reasoning_deltas == ["Check xAI thought."]


@pytest.mark.asyncio
async def test_litellm_stream_patch_forwards_strict_feature_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wrapper should preserve newer Agents SDK stream-handler keyword args."""
    litellm_model = pytest.importorskip("agents.extensions.models.litellm_model")
    patch = importlib.import_module("agency_swarm.streaming.litellm_reasoning")
    seen: dict[str, object] = {}
    chunk = SimpleNamespace(choices=[])

    class Handler:
        @classmethod
        async def handle_stream(
            cls,
            response,
            stream,
            model=None,
            strict_feature_validation: bool = False,
        ):
            seen["response"] = response
            seen["model"] = model
            seen["strict_feature_validation"] = strict_feature_validation
            async for item in stream:
                yield item

    monkeypatch.setattr(litellm_model, "ChatCmplStreamHandler", Handler)
    patch.patch_litellm_thinking_blocks()

    async def stream():
        yield chunk

    events = [
        event
        async for event in Handler.handle_stream(
            "response",
            stream(),
            "model",
            strict_feature_validation=True,
        )
    ]

    assert events == [chunk]
    assert seen == {
        "response": "response",
        "model": "model",
        "strict_feature_validation": True,
    }


def test_litellm_patch_skips_already_normalized_chunks() -> None:
    patch = importlib.import_module("agency_swarm.streaming.litellm_reasoning")
    delta = SimpleNamespace(
        reasoning="OpenRouter text",
        _agency_swarm_skip_reasoning_content_copy=True,
    )
    chunk = SimpleNamespace(choices=[SimpleNamespace(delta=delta)])

    patch._copy_thinking_blocks_to_reasoning_content(chunk)

    assert not hasattr(delta, "reasoning_content")

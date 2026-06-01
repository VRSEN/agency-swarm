import importlib
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_litellm_thinking_blocks_emit_reasoning_events() -> None:
    """LiteLLM thinking_blocks should be visible as reasoning stream deltas."""
    pytest.importorskip("agents.extensions.models.litellm_model")

    importlib.import_module("agency_swarm")
    from agents.extensions.models.litellm_model import ChatCmplStreamHandler
    from openai.types.responses import Response

    async def stream():
        yield SimpleNamespace(
            id="chatcmpl_1",
            model="anthropic/claude-sonnet-4",
            usage=None,
            choices=[
                SimpleNamespace(
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

    importlib.import_module("agency_swarm")
    from agents.extensions.models.litellm_model import ChatCmplStreamHandler
    from openai.types.responses import Response

    async def stream():
        yield SimpleNamespace(
            id="chatcmpl_1",
            model="gemini/gemini-2.5-pro",
            usage=None,
            choices=[
                SimpleNamespace(
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

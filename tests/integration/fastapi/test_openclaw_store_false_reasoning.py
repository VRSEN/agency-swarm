from __future__ import annotations

import copy
from typing import Any

import pytest
from agents.items import TResponseInputItem
from openai import OpenAI

from agency_swarm.integrations.fastapi_utils.endpoint_handlers import (
    ActiveRunRegistry,
    generate_chat_name,
    make_response_endpoint,
    make_stream_endpoint,
)
from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest
from agency_swarm.messages.response_input_sanitizer import (
    REASONING_ENCRYPTED_CONTENT_INCLUDE,
    sanitize_store_false_responses_input,
)
from tests.response_history_helpers import (
    StubRequest,
    TrackingResponsesModel,
    agency_factory_with_store,
    assert_store_false_input_preserves_encrypted_reasoning,
    assert_store_false_input_preserves_stateless_reasoning,
    assert_store_false_requests_encrypted_reasoning,
    assert_unencrypted_reasoning_is_dropped,
    build_store_false_agency_factory,
)
from tests.response_history_samples import (
    history_with_encrypted_reasoning,
    history_with_unencrypted_reasoning,
    history_with_unencrypted_reasoning_before_tool_pair,
)


@pytest.mark.asyncio
async def test_response_endpoint_store_false_requests_and_preserves_encrypted_reasoning() -> None:
    model = TrackingResponsesModel()
    handler = make_response_endpoint(BaseRequest, build_store_false_agency_factory(model), lambda: None)

    await handler(BaseRequest(message="again", chat_history=history_with_encrypted_reasoning()), token=None)

    assert_store_false_requests_encrypted_reasoning(model.seen_model_settings[0])
    assert_store_false_input_preserves_stateless_reasoning(model.seen_inputs[0])


@pytest.mark.asyncio
async def test_stream_endpoint_store_false_drops_only_unencrypted_reasoning() -> None:
    model = TrackingResponsesModel()
    handler = make_stream_endpoint(
        BaseRequest,
        build_store_false_agency_factory(model),
        lambda: None,
        ActiveRunRegistry(),
    )

    response = await handler(
        http_request=StubRequest(),
        request=BaseRequest(message="again", chat_history=history_with_unencrypted_reasoning()),
        token=None,
    )
    _chunks = [chunk async for chunk in response.body_iterator]

    assert_store_false_requests_encrypted_reasoning(model.seen_model_settings[0])
    assert_unencrypted_reasoning_is_dropped(model.seen_inputs[0])


@pytest.mark.asyncio
async def test_stream_endpoint_store_false_drops_legacy_reasoning_span_and_keeps_current_user() -> None:
    model = TrackingResponsesModel()
    handler = make_stream_endpoint(
        BaseRequest,
        build_store_false_agency_factory(model),
        lambda: None,
        ActiveRunRegistry(),
    )
    legacy_history = history_with_unencrypted_reasoning_before_tool_pair()[:-1]

    response = await handler(
        http_request=StubRequest(),
        request=BaseRequest(message="again", chat_history=legacy_history),
        token=None,
    )
    _chunks = [chunk async for chunk in response.body_iterator]

    assert_store_false_requests_encrypted_reasoning(model.seen_model_settings[0])
    assert model.seen_inputs[0] == [{"role": "user", "content": "again", "type": "message"}]


@pytest.mark.asyncio
async def test_agency_store_false_persists_encrypted_reasoning_for_next_run() -> None:
    model = TrackingResponsesModel(include_encrypted_reasoning=True)
    persisted_history: list[dict[str, Any]] = []
    agency = agency_factory_with_store(model, persisted_history, store_false=True)

    await agency.get_response(message="hi")

    stored_reasoning = [item for item in persisted_history if item.get("type") == "reasoning"]
    assert len(stored_reasoning) == 1
    assert stored_reasoning[0]["encrypted_content"] == "encrypted_reasoning"

    await agency.get_response(message="again")

    assert_store_false_input_preserves_encrypted_reasoning(model.seen_inputs[1])


def test_live_openai_store_false_replays_encrypted_reasoning() -> None:
    """Live OpenAI proof for stateless Responses reasoning replay."""
    client = OpenAI()
    first = client.responses.create(
        model="gpt-5.4-nano",
        input="Compute 37*41. Return only the number.",
        store=False,
        include=[REASONING_ENCRYPTED_CONTENT_INCLUDE],
        reasoning={"effort": "high"},
        max_output_tokens=64,
    )
    first_items = [item.model_dump(exclude_none=True) for item in first.output]
    reasoning_items = [item for item in first_items if item.get("type") == "reasoning"]
    output_types = [item.get("type") for item in first_items]
    reasoning_tokens = first.usage.output_tokens_details.reasoning_tokens if first.usage else None
    assert first.output_text.strip() == "1517"
    if not reasoning_items:
        if reasoning_tokens:
            pytest.fail(
                f"OpenAI reported reasoning but returned no reasoning item; got {output_types=} {reasoning_tokens=}"
            )
        pytest.skip(f"OpenAI returned no reasoning output item; got {output_types=} {reasoning_tokens=}")
    assert all(item.get("encrypted_content") for item in reasoning_items)

    replay_input = sanitize_store_false_responses_input(
        [
            *first_items,
            {
                "role": "user",
                "content": "What exact number did you just return? Return only that same number.",
            },
        ]
    )
    second = client.responses.create(
        model="gpt-5.4-nano",
        input=replay_input,
        store=False,
        include=[REASONING_ENCRYPTED_CONTENT_INCLUDE],
        reasoning={"effort": "high"},
        max_output_tokens=64,
    )
    assert second.output_text.strip() == "1517"


@pytest.mark.asyncio
async def test_codex_chat_name_store_false_uses_encrypted_reasoning_include() -> None:
    captured_inputs: list[list[TResponseInputItem]] = []
    captured_includes: list[list[str]] = []

    class _TitleStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _Responses:
        async def create(self, **kwargs: Any) -> _TitleStream:
            captured_inputs.append(copy.deepcopy(kwargs["input"]))
            captured_includes.append(copy.deepcopy(kwargs["include"]))
            return _TitleStream()

    class _Client:
        base_url = "https://chatgpt.com/backend-api/codex"
        responses = _Responses()

    with pytest.raises(ValueError, match="Generated chat name"):
        await generate_chat_name(history_with_encrypted_reasoning(), openai_client=_Client())  # type: ignore[arg-type]

    assert captured_inputs
    assert captured_includes
    assert all(include == [REASONING_ENCRYPTED_CONTENT_INCLUDE] for include in captured_includes)
    assert_store_false_input_preserves_stateless_reasoning(captured_inputs[0])

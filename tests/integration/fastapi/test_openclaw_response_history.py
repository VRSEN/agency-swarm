from __future__ import annotations

import copy
from typing import Any

import pytest

from agency_swarm.integrations.fastapi_utils.endpoint_handlers import (
    ActiveRunRegistry,
    make_response_endpoint,
    make_stream_endpoint,
)
from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest
from tests.response_history_helpers import (
    StubRequest,
    TrackingResponsesModel,
    agency_factory_with_store,
    assert_history_input_has_no_response_ids,
    assert_messages_have_no_response_ids,
    build_agency_factory,
    parse_sse_messages_payload,
)


@pytest.mark.asyncio
async def test_response_endpoint_replays_returned_history_without_hidden_response_ids() -> None:
    model = TrackingResponsesModel()
    handler = make_response_endpoint(BaseRequest, build_agency_factory(model), lambda: None)

    first = await handler(http_request=None, request=BaseRequest(message="hi"), token=None)
    history = copy.deepcopy(first["new_messages"])
    assert_messages_have_no_response_ids(history)

    await handler(http_request=None, request=BaseRequest(message="again", chat_history=history), token=None)

    assert model.seen_previous_response_ids == [None, None]
    assert_history_input_has_no_response_ids(model.seen_inputs[1])


@pytest.mark.asyncio
async def test_stream_endpoint_replays_returned_history_without_hidden_response_ids() -> None:
    model = TrackingResponsesModel()
    handler = make_stream_endpoint(BaseRequest, build_agency_factory(model), lambda: None, ActiveRunRegistry())

    first_response = await handler(http_request=StubRequest(), request=BaseRequest(message="hi"), token=None)
    first_chunks = [chunk async for chunk in first_response.body_iterator]
    first_payload = parse_sse_messages_payload(first_chunks)
    history = copy.deepcopy(first_payload["new_messages"])
    assert_messages_have_no_response_ids(history)

    second_response = await handler(
        http_request=StubRequest(),
        request=BaseRequest(message="again", chat_history=history),
        token=None,
    )
    _second_chunks = [chunk async for chunk in second_response.body_iterator]

    assert model.seen_previous_response_ids == [None, None]
    assert_history_input_has_no_response_ids(model.seen_inputs[1])


@pytest.mark.asyncio
async def test_agency_get_response_persists_history_without_hidden_response_ids() -> None:
    model = TrackingResponsesModel()
    persisted_history: list[dict[str, Any]] = []
    agency = agency_factory_with_store(model, persisted_history)

    await agency.get_response(message="hi")
    assert_messages_have_no_response_ids(persisted_history)
    await agency.get_response(message="again")

    assert model.seen_previous_response_ids == [None, None]
    assert_history_input_has_no_response_ids(model.seen_inputs[1])


@pytest.mark.asyncio
async def test_agency_stream_persists_history_without_hidden_response_ids() -> None:
    model = TrackingResponsesModel()
    persisted_history: list[dict[str, Any]] = []
    agency = agency_factory_with_store(model, persisted_history)

    first_stream = agency.get_response_stream(message="hi")
    _first_events = [event async for event in first_stream]
    assert_messages_have_no_response_ids(persisted_history)

    second_stream = agency.get_response_stream(message="again")
    _second_events = [event async for event in second_stream]

    assert model.seen_previous_response_ids == [None, None]
    assert_history_input_has_no_response_ids(model.seen_inputs[1])

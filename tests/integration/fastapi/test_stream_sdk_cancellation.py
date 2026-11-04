"""Exercise the endpoint through the real Agency and pinned SDK run loop."""

import asyncio
import json
from collections.abc import AsyncIterator

from agents import Tool
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff
from agents.items import TResponseInputItem, TResponseStreamEvent
from agents.model_settings import ModelSettings
from agents.models.interface import ModelTracing
from openai.types.responses import ResponseCreatedEvent
from openai.types.responses.response_prompt_param import ResponsePromptParam

from agency_swarm import Agency, Agent
from agency_swarm.integrations.fastapi_utils import endpoint_handlers
from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, CancelRequest
from agency_swarm.integrations.fastapi_utils.run_registry import ActiveRunRegistry
from tests.deterministic_model import DeterministicModel
from tests.integration.fastapi.test_stream_request_lifecycle import _request


class _PausedModel(DeterministicModel):
    def __init__(self) -> None:
        super().__init__(default_response="completed current turn")
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.closed = asyncio.Event()

    def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        source = super().stream_response(
            system_instructions,
            input,
            model_settings,
            tools,
            output_schema,
            handoffs,
            tracing,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        )

        async def events() -> AsyncIterator[TResponseStreamEvent]:
            try:
                async for event in source:
                    yield event
                    if isinstance(event, ResponseCreatedEvent):
                        self.started.set()
                        await self.release.wait()
            finally:
                self.closed.set()

        return events()


async def test_cancel_after_turn_persists_completed_sdk_turn() -> None:
    model = _PausedModel()
    agency = Agency(Agent(name="SDK lifecycle", instructions="Use the deterministic model", model=model))
    registry = ActiveRunRegistry()
    handler = endpoint_handlers.make_stream_endpoint(BaseRequest, lambda **_: agency, lambda: None, registry)
    cancel = endpoint_handlers.make_cancel_endpoint(CancelRequest, lambda: None, registry)
    response = await handler(http_request=_request(), request=BaseRequest(message="hello"), token=None)
    meta = await anext(response.body_iterator)
    run_id = json.loads(meta.split("data: ", 1)[1])["run_id"]

    async def consume() -> list[str]:
        return [chunk async for chunk in response.body_iterator]

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(model.started.wait(), timeout=2)
    cancellation = asyncio.create_task(cancel(CancelRequest(run_id=run_id, cancel_mode="after_turn"), token=None))
    active = await registry.get(run_id)
    await active.cancel_event.wait()
    model.release.set()
    chunks = await asyncio.wait_for(consumer, timeout=2)
    result = await asyncio.wait_for(cancellation, timeout=2)

    assert model.closed.is_set()
    assert result["cancelled"] is True
    assert result["timed_out"] is False
    assert any("completed current turn" in str(message.get("content")) for message in result["new_messages"])
    assert any("completed current turn" in chunk for chunk in chunks)
    assert active.stream.final_output == "completed current turn"
    assert await registry.get(run_id) is None


async def test_disconnect_cancels_sdk_producer_before_releasing_request() -> None:
    model = _PausedModel()
    agency = Agency(Agent(name="SDK lifecycle", instructions="Use the deterministic model", model=model))
    registry = ActiveRunRegistry()
    handler = endpoint_handlers.make_stream_endpoint(BaseRequest, lambda **_: agency, lambda: None, registry)
    response = await handler(http_request=_request(), request=BaseRequest(message="hello"), token=None)
    meta = await anext(response.body_iterator)
    run_id = json.loads(meta.split("data: ", 1)[1])["run_id"]
    active = await registry.get(run_id)

    async def consume() -> list[str]:
        return [chunk async for chunk in response.body_iterator]

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(model.started.wait(), timeout=2)
    consumer.cancel()
    try:
        await consumer
    except asyncio.CancelledError:
        pass

    assert model.closed.is_set()
    assert active.done_event.is_set()
    assert await registry.get(run_id) is None
    assert await asyncio.wait_for(active.stream.wait_final_result(), timeout=1) is None


async def test_second_cancel_escalates_current_sdk_turn_to_immediate() -> None:
    model = _PausedModel()
    agency = Agency(Agent(name="SDK lifecycle", instructions="Use the deterministic model", model=model))
    registry = ActiveRunRegistry()
    handler = endpoint_handlers.make_stream_endpoint(BaseRequest, lambda **_: agency, lambda: None, registry)
    cancel = endpoint_handlers.make_cancel_endpoint(CancelRequest, lambda: None, registry)
    response = await handler(http_request=_request(), request=BaseRequest(message="hello"), token=None)
    meta = await anext(response.body_iterator)
    run_id = json.loads(meta.split("data: ", 1)[1])["run_id"]

    async def consume() -> list[str]:
        return [chunk async for chunk in response.body_iterator]

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(model.started.wait(), timeout=2)
    graceful = asyncio.create_task(cancel(CancelRequest(run_id=run_id, cancel_mode="after_turn"), token=None))
    active = await registry.get(run_id)
    await active.cancel_event.wait()
    immediate = asyncio.create_task(cancel(CancelRequest(run_id=run_id, cancel_mode="immediate"), token=None))
    first, second, chunks = await asyncio.wait_for(asyncio.gather(graceful, immediate, consumer), timeout=2)

    assert model.closed.is_set()
    assert not model.release.is_set()
    assert first["cancel_mode"] == second["cancel_mode"] == "immediate"
    assert first["cancelled"] and second["cancelled"]
    assert active.done_event.is_set()
    assert not any("completed current turn" in chunk for chunk in chunks)

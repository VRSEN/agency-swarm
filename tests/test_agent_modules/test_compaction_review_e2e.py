"""Independent-review e2e proof for PR 829: model input starts at the latest compaction item."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from agents import ModelSettings, Tool, TResponseInputItem
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff
from agents.items import ModelResponse, TResponseStreamEvent
from agents.models.interface import ModelTracing
from openai.types.responses.response_prompt_param import ResponsePromptParam

from agency_swarm import Agency, Agent
from agency_swarm.agent.agency_session import create_agency_session
from agency_swarm.agent.context_types import AgencyContext
from agency_swarm.utils.thread import ThreadManager
from tests.deterministic_model import DeterministicModel


class CapturingModel(DeterministicModel):
    """DeterministicModel that records the exact input list the model receives."""

    def __init__(self) -> None:
        super().__init__()
        self.captured_inputs: list[str | list[TResponseInputItem]] = []

    async def get_response(
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
    ) -> ModelResponse:
        self.captured_inputs.append(list(input) if isinstance(input, list) else input)
        return await super().get_response(
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
        self.captured_inputs.append(list(input) if isinstance(input, list) else input)
        return super().stream_response(
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


def _user(text: str, **meta: Any) -> TResponseInputItem:
    return {"role": "user", "content": text, **meta}  # type: ignore[return-value]


def _assistant(text: str, **meta: Any) -> TResponseInputItem:
    return {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text}],
        **meta,
    }  # type: ignore[return-value]


def _compaction(item_id: str = "cmp_1", **meta: Any) -> TResponseInputItem:
    return {"type": "compaction", "id": item_id, "encrypted_content": "enc-state", **meta}  # type: ignore[return-value]


def _texts(items: str | list[TResponseInputItem]) -> str:
    if isinstance(items, str):
        return items
    return (
        " ".join(
            part.get("text", "") if isinstance(part, dict) else ""
            for item in items
            if isinstance(item, dict)
            for part in (item.get("content") if isinstance(item.get("content"), list) else [])
        )
        + " "
        + " ".join(
            item.get("content", "") if isinstance(item.get("content"), str) else ""
            for item in items
            if isinstance(item, dict)
        )
    )


@pytest.mark.asyncio
async def test_model_input_starts_at_latest_compaction_item() -> None:
    """[a, b, compaction, c] stored -> the model only sees [compaction, c, new input]."""
    history = [
        _user("message a"),
        _assistant("message b"),
        _compaction(),
        _user("message c"),
    ]
    model = CapturingModel()
    agent = Agent(name="RecallAgent", instructions="test", model=model)
    agency = Agency(agent, load_threads_callback=lambda: [dict(m) for m in history])

    await agency.get_response("next question", "RecallAgent")

    assert model.captured_inputs, "model was never invoked"
    captured = model.captured_inputs[0]
    assert isinstance(captured, list)
    assert captured[0].get("type") == "compaction"
    assert captured[0].get("id") == "cmp_1"
    assert captured[0].get("encrypted_content") == "enc-state"
    body = _texts(captured)
    assert "message a" not in body
    assert "message b" not in body
    assert "message c" in body
    assert "next question" in body


@pytest.mark.asyncio
async def test_model_input_starts_at_latest_compaction_item_streaming() -> None:
    model = CapturingModel()
    history = [_user("a1"), _user("a2"), _compaction(), _assistant("after")]
    agent = Agent(name="RecallAgent", instructions="test", model=model)
    agency = Agency(agent, load_threads_callback=lambda: [dict(m) for m in history])

    stream = agency.get_response_stream("next question", "RecallAgent")
    async for _ in stream:
        pass

    captured = model.captured_inputs[0]
    assert isinstance(captured, list)
    assert captured[0].get("type") == "compaction"
    body = _texts(captured)
    assert "a1" not in body
    assert "a2" not in body


@pytest.mark.asyncio
async def test_pair_slice_compaction_does_not_leak_into_user_thread() -> None:
    """A compaction stored in the (Worker, CEO) pair slice trims only that slice."""
    thread_manager = ThreadManager()
    context = AgencyContext(agency_instance=None, thread_manager=thread_manager, subagents={})
    agent = Agent(name="Worker", instructions="test", model=DeterministicModel())
    thread_manager.add_messages(
        [
            _user("user thread msg", agent="CEO", callerAgent=None),
            _user("pair q", agent="Worker", callerAgent="CEO"),
            _compaction(agent="Worker", callerAgent="CEO"),
            _assistant("pair a", agent="Worker", callerAgent="CEO"),
        ]
    )

    user_session = create_agency_session(
        agent=agent,
        sender_name=None,
        agency_context=context,
        new_input_items=[],
        agent_run_id="r1",
        parent_run_id=None,
        run_trace_id="t1",
        run_config_override=None,
    )
    pair_session = create_agency_session(
        agent=agent,
        sender_name="CEO",
        agency_context=context,
        new_input_items=[],
        agent_run_id="r2",
        parent_run_id=None,
        run_trace_id="t1",
        run_config_override=None,
    )

    user_items = await user_session.get_items()
    assert [item.get("content") for item in user_items] == ["user thread msg"]

    pair_items = await pair_session.get_items()
    assert pair_items[0].get("type") == "compaction"
    assert pair_items[1].get("content") == [{"type": "output_text", "text": "pair a"}]
    assert len(pair_items) == 2

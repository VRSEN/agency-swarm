from __future__ import annotations

import json
import typing
from copy import deepcopy
from dataclasses import dataclass, field

import pytest
from agents.result import RunResult, RunResultStreaming
from agents.run_context import RunContextWrapper
from agents.usage import Usage
from fastapi.testclient import TestClient
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from agency_swarm import Agency, Agent, run_fastapi
from agency_swarm.agent.execution_stream_response import StreamingRunResponse
from agency_swarm.context import MasterContext
from agency_swarm.streaming.utils import StreamingContext
from agency_swarm.utils.thread import ThreadManager


class _HasMainAgentModel(typing.Protocol):
    _main_agent_model: str


@dataclass
class ContextTracker:
    """Keep the latest contexts observed by the test agent."""

    last_response_context: dict[str, str] | None = None
    last_stream_context: dict[str, str | StreamingContext] | None = None

    def reset(self) -> None:
        self.last_response_context = None
        self.last_stream_context = None

    def record_response(self, context: dict[str, str] | None) -> None:
        self.last_response_context = deepcopy(context) if context is not None else None

    def record_stream(self, context: dict[str, str | StreamingContext] | None) -> None:
        self.last_stream_context = deepcopy(context) if context is not None else None


class TrackingAgent(Agent):
    """Agent subclass that records incoming context instead of calling the LLM."""

    def __init__(self, tracker: ContextTracker):
        super().__init__(name="TestAgent", instructions="Base instructions")
        self._tracker = tracker

    async def get_response(
        self,
        message,
        sender_name=None,
        context_override: dict[str, str] | None = None,
        **kwargs: str | int | float | bool | None | list[str],
    ):
        self._tracker.record_response(context_override)
        usage = Usage(
            requests=1,
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            input_tokens_details=InputTokensDetails(cached_tokens=0),
            output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
        )

        thread_manager = ThreadManager()
        master_context = MasterContext(
            thread_manager=thread_manager,
            agents={self.name: self},
            user_context=context_override or {},
            agent_runtime_state={},
            current_agent_name=self.name,
            shared_instructions=None,
        )

        run_result = RunResult(
            input=str(message),
            new_items=[],
            raw_responses=[],
            final_output="Test response",
            input_guardrail_results=[],
            output_guardrail_results=[],
            tool_input_guardrail_results=[],
            tool_output_guardrail_results=[],
            context_wrapper=RunContextWrapper(context=master_context, usage=usage),
            _last_agent=self,
        )
        # Enables cost fallback calculation in calculate_usage_with_cost(...)
        typing.cast(_HasMainAgentModel, run_result)._main_agent_model = "gpt-4o"
        return run_result

    def get_response_stream(
        self,
        message,
        sender_name=None,
        context_override: dict[str, str | StreamingContext] | None = None,
        **kwargs: str | int | float | bool | None | list[str],
    ):
        self._tracker.record_stream(context_override)

        usage = Usage(
            requests=1,
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            input_tokens_details=InputTokensDetails(cached_tokens=0),
            output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
        )
        thread_manager = ThreadManager()
        master_context = MasterContext(
            thread_manager=thread_manager,
            agents={self.name: self},
            user_context=(context_override or {}),
            agent_runtime_state={},
            current_agent_name=self.name,
            shared_instructions=None,
        )

        final_result = RunResultStreaming(
            input=str(message),
            new_items=[],
            raw_responses=[],
            final_output="Test response",
            input_guardrail_results=[],
            output_guardrail_results=[],
            tool_input_guardrail_results=[],
            tool_output_guardrail_results=[],
            context_wrapper=RunContextWrapper(context=master_context, usage=usage),
            current_agent=self,
            current_turn=1,
            max_turns=1,
            _current_agent_output_schema=None,
            trace=None,
        )
        typing.cast(_HasMainAgentModel, final_result)._main_agent_model = "gpt-4o"

        stream_ref: dict[str, StreamingRunResponse] = {}

        async def _generator():
            yield {"type": "text", "data": "Test"}
            # Make final_result available to the FastAPI endpoint handler.
            stream_ref["stream"]._resolve_final_result(final_result)  # noqa: SLF001

        stream = StreamingRunResponse(_generator())
        stream_ref["stream"] = stream
        return stream


@dataclass
class RecordingAgencyFactory:
    """Factory that creates agencies with context-tracking agents."""

    tracker: ContextTracker = field(default_factory=ContextTracker)

    def __call__(self, load_threads_callback=None, save_threads_callback=None):
        self.tracker.reset()
        agent = TrackingAgent(self.tracker)
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )


@pytest.fixture
def recording_agency_factory() -> RecordingAgencyFactory:
    return RecordingAgencyFactory()


def test_non_streaming_user_context(recording_agency_factory: RecordingAgencyFactory):
    """Ensure user_context is forwarded to non-streaming endpoint."""
    app = run_fastapi(agencies={"test_agency": recording_agency_factory}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.post(
        "/test_agency/get_response",
        json={"message": "Hello", "user_context": {"plan": "pro", "user_id": "123"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "usage" in payload
    usage = payload["usage"]
    assert usage["request_count"] == 1
    assert usage["input_tokens"] == 10
    assert usage["output_tokens"] == 20
    assert usage["total_tokens"] == 30
    assert isinstance(usage["total_cost"], int | float)
    assert recording_agency_factory.tracker.last_response_context == {"plan": "pro", "user_id": "123"}


def test_streaming_user_context(recording_agency_factory: RecordingAgencyFactory):
    """Ensure user_context is forwarded to streaming endpoint."""
    app = run_fastapi(agencies={"test_agency": recording_agency_factory}, return_app=True, app_token_env="")
    client = TestClient(app)

    with client.stream(
        "POST",
        "/test_agency/get_response_stream",
        json={"message": "Hello", "user_context": {"plan": "pro"}},
    ) as response:
        assert response.status_code == 200
        lines = list(response.iter_lines())

    stream_context = recording_agency_factory.tracker.last_stream_context
    assert stream_context is not None
    assert {k: v for k, v in stream_context.items() if k != "_streaming_context"} == {"plan": "pro"}
    assert "_streaming_context" in stream_context

    # Assert the final messages SSE event contains usage
    current_event: str | None = None
    messages_payloads = []
    for raw in lines:
        if not raw:
            continue
        line = raw.decode("utf-8") if isinstance(raw, bytes | bytearray) else raw
        if line.startswith("event:"):
            current_event = line.split("event:", 1)[1].strip()
            continue
        if not line.startswith("data:"):
            continue
        data_str = line.split("data:", 1)[1].strip()
        if data_str == "[DONE]":
            continue
        if current_event != "messages":
            continue
        try:
            payload = json.loads(data_str)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            messages_payloads.append(payload)

    assert messages_payloads, "Expected a final 'messages' SSE event payload"
    usage = messages_payloads[-1]["usage"]
    assert usage["request_count"] == 1
    assert usage["input_tokens"] == 10
    assert usage["output_tokens"] == 20
    assert usage["total_tokens"] == 30
    assert isinstance(usage["total_cost"], int | float)


def test_agui_user_context(recording_agency_factory: RecordingAgencyFactory):
    """Ensure AG-UI streaming endpoint forwards user_context."""
    app = run_fastapi(
        agencies={"test_agency": recording_agency_factory},
        return_app=True,
        app_token_env="",
        enable_agui=True,
    )
    client = TestClient(app)

    agui_payload = {
        "thread_id": "test_thread",
        "run_id": "test_run",
        "state": None,
        "messages": [{"id": "msg1", "role": "user", "content": "Hello"}],
        "tools": [],
        "context": [],
        "forwardedProps": None,
        "user_context": {"plan": "pro", "customer_tier": "gold"},
    }

    with client.stream("POST", "/test_agency/get_response_stream", json=agui_payload) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    stream_context = recording_agency_factory.tracker.last_stream_context
    assert stream_context is not None
    assert {k: v for k, v in stream_context.items() if k != "_streaming_context"} == {
        "plan": "pro",
        "customer_tier": "gold",
    }
    assert "_streaming_context" in stream_context


def test_user_context_defaults_to_none(recording_agency_factory: RecordingAgencyFactory):
    """Requests without user_context should not inject overrides."""
    app = run_fastapi(agencies={"test_agency": recording_agency_factory}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.post("/test_agency/get_response", json={"message": "Hello"})

    assert response.status_code == 200
    assert recording_agency_factory.tracker.last_response_context is None

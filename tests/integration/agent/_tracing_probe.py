"""Run real framework calls with HTTP intercepted, in an isolated process."""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from unittest.mock import patch

import httpx2
from agents import (
    Agent as SDKAgent,
    GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered,
    OpenAIResponsesModel,
    RunConfig,
    RunContextWrapper,
    TResponseInputItem,
    handoff,
    input_guardrail,
    set_default_openai_client,
    set_trace_processors,
    set_tracing_disabled,
    trace,
)
from agents.models.multi_provider import MultiProvider, MultiProviderMap
from agents.models.openai_provider import OpenAIProvider
from agents.run_state import RunState
from agents.tracing import get_trace_provider
from agents.tracing.processors import BackendSpanExporter, BatchTraceProcessor
from openai import AsyncOpenAI
from openai.types.responses import Response, ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

from agency_swarm import Agency, Agent, Runner

CUSTOM_BASE = "http://127.0.0.1:9999/v1"
OPENAI_BASE = "https://api.openai.com/v1"
COLLECTOR = "http://collector.test/traces/ingest"


def _response() -> Response:
    return Response(
        id="resp_offline",
        created_at=0,
        model="gpt-4o-mini",
        object="response",
        status="completed",
        parallel_tool_calls=True,
        tool_choice="auto",
        tools=[],
        output=[
            ResponseOutputMessage(
                id="msg_offline",
                type="message",
                role="assistant",
                status="completed",
                content=[ResponseOutputText(type="output_text", text="offline reply", annotations=[])],
            )
        ],
    )


def _stream_body(response: Response) -> bytes:
    data = response.model_dump(mode="json")
    events = [
        {
            "type": "response.created",
            "sequence_number": 0,
            "response": {**data, "status": "in_progress", "output": [], "usage": None},
        },
        {"type": "response.output_item.added", "sequence_number": 1, "output_index": 0, "item": data["output"][0]},
        {"type": "response.output_item.done", "sequence_number": 2, "output_index": 0, "item": data["output"][0]},
        {"type": "response.completed", "sequence_number": 3, "response": data},
    ]
    return "".join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events).encode()


@dataclass
class RecordingHTTP:
    model_requests: list[str] = field(default_factory=list)
    trace_requests: list[str] = field(default_factory=list)
    trace_item_counts: list[int] = field(default_factory=list)

    async def model_send(self, request: httpx2.Request) -> httpx2.Response:
        self.model_requests.append(str(request.url))
        assert request.method == "POST" and request.url.path == "/v1/responses"
        response = _response()
        body = json.loads(request.content)
        if any(tool.get("name") == "transfer_to_proxy" for tool in body.get("tools", [])):
            response.output = [
                ResponseFunctionToolCall(
                    arguments="{}",
                    call_id="call_proxy",
                    name="transfer_to_proxy",
                    id="fc_proxy",
                    status="completed",
                    type="function_call",
                )
            ]
        if (
            any(tool.get("name") == "send_message" for tool in body.get("tools", []))
            and not any(item.get("type") == "function_call_output" for item in body.get("input", []))
            and len(self.model_requests) <= 2
        ):
            tool = next(tool for tool in body["tools"] if tool.get("name") == "send_message")
            recipient = tool["parameters"]["properties"]["recipient_agent"]["enum"][0]
            response.output = [
                ResponseFunctionToolCall(
                    arguments=json.dumps(
                        {"recipient_agent": recipient, "message": "Reply offline.", "additional_instructions": ""}
                    ),
                    call_id=f"call_send_{len(self.model_requests)}",
                    name="send_message",
                    id=f"fc_send_{len(self.model_requests)}",
                    status="completed",
                    type="function_call",
                )
            ]
        if body.get("stream"):
            return httpx2.Response(
                200,
                content=_stream_body(response),
                headers={"content-type": "text/event-stream"},
                request=request,
            )
        return httpx2.Response(200, json=response.model_dump(mode="json"), request=request)

    def trace_send(self, request: httpx2.Request) -> httpx2.Response:
        self.trace_requests.append(str(request.url))
        self.trace_item_counts.append(len(json.loads(request.content)["data"]))
        return httpx2.Response(200, json={}, request=request)


def _explicit_model(base_url: str) -> OpenAIResponsesModel:
    return OpenAIResponsesModel(
        "gpt-4o-mini",
        openai_client=AsyncOpenAI(api_key="sk-offline-test", base_url=base_url),
    )


def _case(scenario: str) -> tuple[Agent, RunConfig | None]:
    config: RunConfig | None = None
    agent = Agent(name="EndpointProbe", instructions="Reply briefly.", model="gpt-4o-mini")
    if scenario in {"explicit_model", "mixed"}:
        agent.model = _explicit_model(CUSTOM_BASE)
    elif scenario == "model_override":
        config = RunConfig(model=_explicit_model(CUSTOM_BASE))
    elif scenario in {"provider", "native_override"}:
        endpoint = OPENAI_BASE if scenario == "native_override" else CUSTOM_BASE
        config = RunConfig(model_provider=OpenAIProvider(api_key="sk-offline-test", base_url=endpoint))
    elif scenario == "mapped_provider":
        providers = MultiProviderMap()
        providers.add_provider("proxy", OpenAIProvider(api_key="sk-offline-test", base_url=CUSTOM_BASE))
        config = RunConfig(model_provider=MultiProvider(provider_map=providers))
        agent.model = "proxy/gpt-4o-mini"
    elif scenario == "default_client":
        set_default_openai_client(
            AsyncOpenAI(api_key="sk-offline-test", base_url=CUSTOM_BASE),
            use_for_tracing=False,
        )
    elif scenario == "config_disabled":
        config = RunConfig(tracing_disabled=True)
    elif scenario == "config_enabled":
        config = RunConfig(tracing={"api_key": "sk-offline-tracing"})
    elif scenario in {"handoff", "wrapped_handoff"}:
        target = Agent(name="Proxy", instructions="Reply briefly.", model=_explicit_model(CUSTOM_BASE))
        agent.handoffs = [handoff(target) if scenario == "wrapped_handoff" else target]
    return agent, config


def _configure_tracing(scenario: str) -> None:
    if scenario == "manual_enabled":
        set_tracing_disabled(False)
    elif scenario == "manual_disabled":
        set_tracing_disabled(True)
    elif scenario == "custom_collector":
        set_trace_processors(
            [
                BatchTraceProcessor(
                    BackendSpanExporter(endpoint=COLLECTOR, api_key="sk-offline-tracing"),
                    schedule_delay=3600,
                )
            ]
        )


async def _respond(
    agent: Agent,
    config: RunConfig | None,
    streamed: bool,
    entrypoint: str,
    state: RunState | None = None,
) -> str:
    message = state if state is not None else "Reply offline."
    if entrypoint == "runner_sync":
        result = await asyncio.to_thread(Runner.run_sync, agent, message, run_config=config)
    elif entrypoint == "runner":
        if streamed:
            result = Runner.run_streamed(agent, message, run_config=config)
            async for _event in result.stream_events():
                pass
        else:
            result = await Runner.run(agent, message, run_config=config)
    else:
        agency = Agency(agent)
        if streamed:
            stream = agency.get_response_stream("Reply offline.", run_config_override=config)
            async for _event in stream:
                pass
            result = stream.final_result
            assert result is not None
        else:
            result = await agency.get_response("Reply offline.", run_config=config)
    assert result.final_output == "offline reply"
    return result.final_output


async def _reject(
    context: RunContextWrapper[None],
    agent: SDKAgent[None],
    value: str | list[TResponseInputItem],
) -> GuardrailFunctionOutput:
    return GuardrailFunctionOutput(output_info="blocked offline", tripwire_triggered=True)


async def _guardrail_probe(scenario: str, streamed: bool) -> str:
    model = "litellm/foo" if scenario == "optional_guardrail" else "gpt-4o-mini"
    agent = SDKAgent(name="Guarded", model=model, input_guardrails=[input_guardrail(_reject, run_in_parallel=False)])
    try:
        if streamed:
            result = Runner.run_streamed(agent, "Blocked input")
            async for _event in result.stream_events():
                pass
        else:
            await Runner.run(agent, "Blocked input")
    except InputGuardrailTripwireTriggered:
        return "blocked"
    raise AssertionError("Input guardrail did not reject")


async def _run_case(scenario: str, streamed: bool, entrypoint: str) -> str:
    if scenario in {"send_message", "send_message_override", "send_message_cycle"}:
        return await _send_message_probe(scenario, streamed)
    if scenario in {"no_key_guardrail", "optional_guardrail"}:
        return await _guardrail_probe(scenario, streamed)
    agent, config = _case(scenario)
    original_disabled = config.tracing_disabled if config is not None else None
    if scenario == "resumed":
        current = Agent(name="Proxy", instructions="Reply briefly.", model=_explicit_model(CUSTOM_BASE))
        state = RunState(RunContextWrapper(None), "Reply offline.", starting_agent=current)
        state._starting_agent = agent
        output = await _respond(agent, config, streamed, "runner", state)
    elif scenario == "outer_trace":
        with trace("Explicit caller trace"):
            output = await _respond(agent, config, streamed, entrypoint)
    else:
        output = await _respond(agent, config, streamed, entrypoint)
    if config is not None:
        assert config.tracing_disabled == original_disabled, "Caller config was mutated"
    return output


async def _send_message_probe(scenario: str, streamed: bool) -> str:
    native_model = _explicit_model(OPENAI_BASE)
    native = Agent(name="Native", instructions="Delegate to Proxy.", model=native_model)
    proxy = Agent(name="Proxy", instructions="Reply briefly.", model=_explicit_model(CUSTOM_BASE))
    flows = [native > proxy]
    if scenario == "send_message_cycle":
        native.model = _explicit_model(CUSTOM_BASE)
        proxy.model = native_model
        flows.append(proxy > native)
    agency = Agency(native, communication_flows=flows)
    config = RunConfig(model=native_model) if scenario in {"send_message_override", "send_message_cycle"} else None
    if streamed:
        stream = agency.get_response_stream("Reply offline.", run_config_override=config)
        async for _event in stream:
            pass
        result = stream.final_result
        assert result is not None
    else:
        result = await agency.get_response("Reply offline.", run_config=config)
    assert result.final_output == "offline reply"
    return result.final_output


async def _probe(scenario: str, streamed: bool, entrypoint: str) -> dict[str, object]:
    recording = RecordingHTTP()

    async def model_send(client: httpx2.AsyncClient, request: httpx2.Request, **kwargs: object) -> httpx2.Response:
        return await recording.model_send(request)

    def trace_send(client: httpx2.Client, request: httpx2.Request, **kwargs: object) -> httpx2.Response:
        return recording.trace_send(request)

    with (
        patch.object(httpx2.AsyncClient, "send", model_send),
        patch.object(httpx2.Client, "send", trace_send),
        patch("socket.socket.connect", side_effect=AssertionError("Unexpected real network connection")),
    ):
        _configure_tracing(scenario)
        output = await _run_case(scenario, streamed, entrypoint)
        provider = get_trace_provider()
        provider.force_flush()
        first_trace_count = len(recording.trace_requests)
        if scenario == "mixed":
            agent, _config = _case("mixed")
            agent.model = _explicit_model(OPENAI_BASE)
            await _respond(agent, None, streamed, entrypoint)
            provider.force_flush()
        provider.shutdown()
    return {
        "output": output,
        "model_requests": recording.model_requests,
        "trace_requests": recording.trace_requests,
        "trace_item_counts": recording.trace_item_counts,
        "first_trace_count": first_trace_count,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(_probe(sys.argv[1], sys.argv[2] == "1", sys.argv[3]))))

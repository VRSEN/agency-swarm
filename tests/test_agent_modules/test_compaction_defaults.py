import json
from typing import Any

import httpx2
from agents import ModelSettings, OpenAIResponsesModel, RunConfig
from openai import AsyncOpenAI

from agency_swarm import Agency, Agent

_USER_CONTEXT_MANAGEMENT = [{"type": "compaction", "compact_threshold": 50_000}]


def test_openai_model_gets_server_side_compaction_by_default() -> None:
    agent = Agent(name="A", instructions="test", model="gpt-6-luna")

    assert agent.model_settings.context_management == [{"type": "compaction", "compact_threshold": 240_000}]


def test_known_model_uses_sdk_context_window_threshold() -> None:
    agent = Agent(name="A", instructions="test", model="gpt-4o")

    assert agent.model_settings.context_management == [{"type": "compaction", "compact_threshold": 115_200}]


def test_explicit_empty_context_management_disables_compaction() -> None:
    agent = Agent(
        name="A", instructions="test", model="gpt-6-luna", model_settings=ModelSettings(context_management=[])
    )

    assert agent.model_settings.context_management == []


def test_non_openai_model_gets_no_compaction() -> None:
    agent = Agent(name="A", instructions="test", model="litellm/gemini/gemini-3.8-flash")

    assert agent.model_settings.context_management is None


def test_context_management_in_extra_args_replaces_compaction_default() -> None:
    agent = Agent(
        name="A",
        instructions="test",
        model="gpt-6-luna",
        model_settings=ModelSettings(extra_args={"context_management": _USER_CONTEXT_MANAGEMENT}),
    )

    assert agent.model_settings.context_management is None
    assert agent.model_settings.extra_args == {"context_management": _USER_CONTEXT_MANAGEMENT}


def _completed_response(model: str) -> dict[str, Any]:
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "model": model,
        "status": "completed",
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "output": [
            {
                "type": "message",
                "id": "msg_1",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "ok", "annotations": []}],
            }
        ],
        "usage": {
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


async def test_context_management_in_extra_args_reaches_responses_api_once() -> None:
    """1.11 agents that set context_management through extra_args must not fail every run."""
    requests: list[dict[str, Any]] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        requests.append(body)
        return httpx2.Response(200, json=_completed_response(body["model"]))

    client = AsyncOpenAI(
        api_key="test-key", max_retries=0, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle))
    )
    agent = Agent(
        name="A",
        instructions="test",
        model=OpenAIResponsesModel(model="gpt-6-luna", openai_client=client),
        model_settings=ModelSettings(extra_args={"context_management": _USER_CONTEXT_MANAGEMENT}),
    )

    result = await Agency(agent).get_response("hi", run_config=RunConfig(tracing_disabled=True))

    assert result.final_output == "ok"
    assert [body["context_management"] for body in requests] == [_USER_CONTEXT_MANAGEMENT]

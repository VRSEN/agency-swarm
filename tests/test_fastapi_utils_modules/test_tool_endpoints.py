from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pytest
from agents import FunctionTool
from agents.tool_context import ToolContext
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agency_swarm.integrations.fastapi_utils.tool_endpoints import make_tool_endpoint
from agency_swarm.tools import BaseTool


class TimestampModel(BaseModel):
    timestamp: datetime


class DummyTypedTool:
    name = "TimestampTool"
    openai_schema = {
        "parameters": {
            "type": "object",
            "properties": {
                "timestamp": {
                    "type": "string",
                    "description": "ISO timestamp",
                }
            },
            "required": ["timestamp"],
        }
    }

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.contexts: list[Any] = []

    async def on_invoke_tool(self, context, input_json: str):
        self.contexts.append(context)
        self.calls.append(input_json)
        return "ok"


def _fake_verify_token():
    return "token"


class _DummyRequest:
    def __init__(self, payload: dict[str, Any], *, explode: bool = False) -> None:
        self.payload = payload
        self.explode = explode

    async def json(self) -> dict[str, Any]:
        if self.explode:
            raise ValueError("bad json")
        return self.payload


class EchoTool(BaseTool):
    text: str

    def run(self) -> str:
        return self.text


class AsyncEchoTool(BaseTool):
    text: str

    async def run(self) -> str:
        return self.text.upper()


class FailingTool(BaseTool):
    text: str

    def run(self) -> str:
        raise RuntimeError("run failed")


@pytest.mark.asyncio
async def test_make_tool_endpoint_serializes_non_json_types(monkeypatch):
    tool = DummyTypedTool()

    def fake_build_request_model(*_, **__):
        return TimestampModel

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.tool_endpoints.build_request_model",
        fake_build_request_model,
    )

    raw_context = {"scope": "raw"}
    handler = make_tool_endpoint(tool, verify_token=_fake_verify_token, context=raw_context)
    request_data = TimestampModel(timestamp="2024-05-01T09:30:00Z")

    response = await handler(request_data=request_data, token="ignored")

    assert response == {"response": "ok"}
    assert tool.calls, "on_invoke_tool should receive serialized payload"
    assert tool.contexts == [raw_context]
    payload = json.loads(tool.calls[0])
    assert payload == {"timestamp": "2024-05-01T09:30:00Z"}


@pytest.mark.asyncio
async def test_make_tool_endpoint_generic_handler_for_sync_callable() -> None:
    def echo(value: str) -> str:
        return f"echo:{value}"

    handler = make_tool_endpoint(echo, verify_token=_fake_verify_token, context=None)
    response = await handler(request=_DummyRequest({"value": "ok"}), token="ignored")
    assert response == {"response": "echo:ok"}


@pytest.mark.asyncio
async def test_make_tool_endpoint_generic_handler_for_async_callable() -> None:
    async def echo_async(value: str) -> str:
        return f"async:{value}"

    handler = make_tool_endpoint(echo_async, verify_token=_fake_verify_token, context=None)
    response = await handler(request=_DummyRequest({"value": "ok"}), token="ignored")
    assert response == {"response": "async:ok"}


@pytest.mark.asyncio
async def test_make_tool_endpoint_generic_handler_returns_json_error() -> None:
    def failing_tool(value: str) -> str:  # noqa: ARG001
        raise RuntimeError("tool failed")

    handler = make_tool_endpoint(failing_tool, verify_token=_fake_verify_token, context=None)
    response = await handler(request=_DummyRequest({"value": "ok"}), token="ignored")
    assert isinstance(response, JSONResponse)
    assert response.status_code == 500
    assert b"tool failed" in response.body


@pytest.mark.asyncio
async def test_make_tool_endpoint_generic_handler_handles_invalid_request_json() -> None:
    handler = make_tool_endpoint(lambda value: value, verify_token=_fake_verify_token, context=None)
    response = await handler(request=_DummyRequest({"value": "ok"}, explode=True), token="ignored")
    assert isinstance(response, JSONResponse)
    assert response.status_code == 500
    assert b"bad json" in response.body


class GenericInvokeTool:
    name = "GenericInvokeTool"

    def __init__(self) -> None:
        self.contexts: list[Any] = []
        self.calls: list[str] = []

    async def on_invoke_tool(self, context, input_json: str):
        self.contexts.append(context)
        self.calls.append(input_json)
        return "ok"


@pytest.mark.asyncio
async def test_make_tool_endpoint_generic_handler_preserves_raw_context_for_non_function_tool() -> None:
    tool = GenericInvokeTool()
    raw_context = {"scope": "raw"}

    handler = make_tool_endpoint(tool, verify_token=_fake_verify_token, context=raw_context)
    response = await handler(request=_DummyRequest({"value": "ok"}), token="ignored")

    assert response == {"response": "ok"}
    assert tool.contexts == [raw_context]
    assert json.loads(tool.calls[0]) == {"value": "ok"}


@pytest.mark.asyncio
async def test_make_tool_endpoint_for_base_tool_sync_and_async_runs() -> None:
    sync_handler = make_tool_endpoint(EchoTool, verify_token=_fake_verify_token, context=None)
    async_handler = make_tool_endpoint(AsyncEchoTool, verify_token=_fake_verify_token, context=None)

    sync_response = await sync_handler(request_data=EchoTool(text="hi"), token="ignored")
    async_response = await async_handler(request_data=AsyncEchoTool(text="hi"), token="ignored")

    assert sync_response == {"response": "hi"}
    assert async_response == {"response": "HI"}


@pytest.mark.asyncio
async def test_make_tool_endpoint_for_base_tool_returns_json_error() -> None:
    handler = make_tool_endpoint(FailingTool, verify_token=_fake_verify_token, context=None)
    response = await handler(request_data=FailingTool(text="hi"), token="ignored")
    assert isinstance(response, JSONResponse)
    assert response.status_code == 500
    assert b"run failed" in response.body


class ParamsModel(BaseModel):
    value: str


class ParamsTool:
    name = "ParamsTool"
    params_json_schema = {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}
    strict_json_schema = True

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, value: str) -> str:
        self.calls.append(value)
        return value.upper()


@pytest.mark.asyncio
async def test_make_tool_endpoint_supports_params_json_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = ParamsTool()
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.tool_endpoints.build_request_model",
        lambda *_args, **_kwargs: ParamsModel,
    )

    handler = make_tool_endpoint(tool, verify_token=_fake_verify_token, context=None)
    response = await handler(request_data=ParamsModel(value="ok"), token="ignored")

    assert response == {"response": "OK"}
    assert tool.calls == ["ok"]


@pytest.mark.asyncio
async def test_make_tool_endpoint_wraps_context_for_sdk_function_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    contexts: list[ToolContext[Any]] = []
    payloads: list[str] = []

    async def on_invoke_tool(context: ToolContext[Any], input_json: str) -> str:
        contexts.append(context)
        payloads.append(input_json)
        return "ok"

    tool = FunctionTool(
        name="SdkFunctionTool",
        description="desc",
        params_json_schema={"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
        on_invoke_tool=on_invoke_tool,
    )
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.tool_endpoints.build_request_model",
        lambda *_args, **_kwargs: ParamsModel,
    )

    raw_context = {"scope": "raw"}
    handler = make_tool_endpoint(tool, verify_token=_fake_verify_token, context=raw_context)
    response = await handler(request_data=ParamsModel(value="ok"), token="ignored")

    assert response == {"response": "ok"}
    assert len(contexts) == 1
    assert isinstance(contexts[0], ToolContext)
    assert contexts[0].context is raw_context
    assert contexts[0].tool_name == "SdkFunctionTool"
    assert contexts[0].tool_arguments == payloads[0]
    assert json.loads(payloads[0]) == {"value": "ok"}

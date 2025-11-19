from __future__ import annotations

import json
from datetime import datetime

import pytest
from pydantic import BaseModel

from agency_swarm.integrations.fastapi_utils.tool_endpoints import make_tool_endpoint


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

    async def on_invoke_tool(self, context, input_json: str):
        self.calls.append(input_json)
        return "ok"


def _fake_verify_token():
    return "token"


@pytest.mark.asyncio
async def test_make_tool_endpoint_serializes_non_json_types(monkeypatch):
    tool = DummyTypedTool()

    def fake_build_request_model(*_, **__):
        return TimestampModel

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.tool_endpoints.build_request_model",
        fake_build_request_model,
    )

    handler = make_tool_endpoint(tool, verify_token=_fake_verify_token, context=None)
    request_data = TimestampModel(timestamp="2024-05-01T09:30:00Z")

    response = await handler(request_data=request_data, token="ignored")

    assert response == {"response": "ok"}
    assert tool.calls, "on_invoke_tool should receive serialized payload"
    payload = json.loads(tool.calls[0])
    assert payload == {"timestamp": "2024-05-01T09:30:00Z"}

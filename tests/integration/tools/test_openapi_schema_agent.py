import json
from pathlib import Path

import httpx
import pytest

from agency_swarm import Agent

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "tests" / "data" / "schemas" / "pastebin.json"


@pytest.mark.asyncio
async def test_agent_calls_pastebin_tool(monkeypatch):
    """Agent should load schema from folder, apply headers, and send JSON-serializable payload."""
    captured = {}

    async def fake_request(self, method, url, **kwargs):
        json_payload = kwargs.get("json")
        if json_payload is not None:
            json.dumps(json_payload)  # raises TypeError when payload contains non-serializable values
        captured.update({"method": method, "url": url, **kwargs})

        class Response:
            def json(self):
                return {"ok": True, "payload": kwargs.get("json")}

        return Response()

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request, raising=False)

    agent = Agent(
        name="PasteAgent",
        instructions="Use the pastebin tool.",
        model="gpt-5-mini",
        schemas_folder=str(SCHEMA_PATH.parent),
        api_headers={"pastebin.json": {"Authorization": "Bearer test-token"}},
    )

    paste_tool = next(tool for tool in agent.tools if tool.name == "createPaste")

    payload = {
        "requestBody": {
            "title": "Test Note",
            "content": "This is a paste.",
            "visibility": "public",
        }
    }

    result = await paste_tool.on_invoke_tool(None, json.dumps(payload))

    assert result["ok"] is True
    assert captured["headers"]["Authorization"] == "Bearer test-token"
    assert captured["json"]["visibility"] == "public"
    assert isinstance(captured["json"]["visibility"], str)

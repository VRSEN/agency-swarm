"""Validate that tool endpoints publish accurate OpenAPI request bodies."""

import pytest

pytest.importorskip("fastapi.testclient")

from agents import function_tool
from fastapi.testclient import TestClient

from agency_swarm import Agency, Agent, BaseTool, run_fastapi


class GreetingTool(BaseTool):
    """Return a repeated greeting."""

    message: str
    count: int = 1

    def run(self) -> str:
        return " ".join([self.message] * self.count)


@function_tool
async def emphasize(text: str, level: int = 1) -> str:
    """Add exclamation marks to the text."""
    return f"{text}{'!' * level}"


def _create_agency(load_threads_callback=None, save_threads_callback=None):
    agent = Agent(name="Greeter", instructions="Greet people politely.")
    return Agency(
        agent,
        name="greeter_agency",
        load_threads_callback=load_threads_callback,
        save_threads_callback=save_threads_callback,
    )


def test_openapi_includes_tool_schemas():
    app = run_fastapi(
        agencies={"greeter": _create_agency},
        tools=[GreetingTool, emphasize],
        return_app=True,
        app_token_env="",
    )
    client = TestClient(app)

    response = client.get("/openapi.json")
    assert response.status_code == 200
    openapi_doc = response.json()

    function_schema_ref = (
        openapi_doc
        ["paths"]
        ["/tool/emphasize"]
        ["post"]
        ["requestBody"]
        ["content"]
        ["application/json"]
        ["schema"]
    )
    assert set(function_schema_ref) == {"$ref"}
    function_schema = openapi_doc["components"]["schemas"]["EmphasizeArgs"]
    assert function_schema["type"] == "object"
    assert set(function_schema["properties"]) == {"text", "level"}
    assert "text" in function_schema["required"]

    basetool_schema_ref = (
        openapi_doc
        ["paths"]
        ["/tool/GreetingTool"]
        ["post"]
        ["requestBody"]
        ["content"]
        ["application/json"]
        ["schema"]
    )
    assert set(basetool_schema_ref) == {"$ref"}
    basetool_schema = openapi_doc["components"]["schemas"]["GreetingTool"]
    assert basetool_schema["type"] == "object"
    assert set(basetool_schema["properties"]) == {"message", "count"}
    assert "message" in basetool_schema["required"]

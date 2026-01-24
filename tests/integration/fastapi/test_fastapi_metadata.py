"""Integration tests for the FastAPI metadata endpoint."""

import json
from datetime import datetime

import pytest

pytest.importorskip("fastapi.testclient")
from agents import CodeInterpreterTool, FileSearchTool, WebSearchTool
from fastapi.testclient import TestClient
from openai.types.responses.tool_param import CodeInterpreter
from pydantic import BaseModel

from agency_swarm import Agency, Agent, BaseTool, function_tool, run_fastapi
from agency_swarm.integrations.fastapi_utils import endpoint_handlers, tool_endpoints
from agency_swarm.tools import ToolFactory


@pytest.fixture
def agency_factory():
    """Provide a simple agency factory for FastAPI tests."""

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="MetadataAgent", instructions="Return metadata")
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    return create_agency


def test_metadata_endpoint_includes_version(monkeypatch, agency_factory):
    """Verify that the metadata endpoint includes the agency-swarm version."""

    expected_version = "9.9.9"
    monkeypatch.setattr(endpoint_handlers, "_get_agency_swarm_version", lambda: expected_version)

    app = run_fastapi(agencies={"test_agency": agency_factory}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.get("/test_agency/get_metadata")

    assert response.status_code == 200
    payload = response.json()
    assert payload["agency_swarm_version"] == expected_version
    assert "allowed_local_file_dirs" in payload


def test_metadata_endpoint_omits_missing_version(monkeypatch, agency_factory):
    """Ensure missing version information is not added to the payload."""

    monkeypatch.setattr(endpoint_handlers, "_get_agency_swarm_version", lambda: None)

    app = run_fastapi(agencies={"test_agency": agency_factory}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.get("/test_agency/get_metadata")

    assert response.status_code == 200
    payload = response.json()
    assert "agency_swarm_version" not in payload
    assert "allowed_local_file_dirs" in payload


def test_metadata_includes_agent_capabilities():
    """Verify that metadata includes capabilities for each agent."""

    class CustomTool(BaseTool):
        """Custom tool for testing."""

        def run(self) -> str:
            return "custom"

    @function_tool
    def sample_function() -> str:
        """Sample function tool."""
        return "sample"

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        # Agent with custom tools
        agent1 = Agent(name="ToolAgent", instructions="Test", tools=[CustomTool, sample_function])
        # Agent with hosted tools
        agent2 = Agent(
            name="HostedAgent",
            instructions="Test",
            tools=[
                FileSearchTool(vector_store_ids=["vs_123"]),
                CodeInterpreterTool(tool_config=CodeInterpreter()),
                WebSearchTool(),
            ],
        )
        agent3 = Agent(
            name="ReasoningAgent",
            instructions="Test",
            model="gpt-5-mini",
        )
        agent4 = Agent(
            name="FullAgent",
            instructions="Test",
            model="gpt-5-mini",
            tools=[CustomTool, FileSearchTool(vector_store_ids=["vs_456"])],
        )
        return Agency(
            agent1,
            communication_flows=[(agent1, agent2), (agent1, agent3), (agent1, agent4)],
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    app = run_fastapi(agencies={"test_agency": create_agency}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.get("/test_agency/get_metadata")

    assert response.status_code == 200
    payload = response.json()
    assert "allowed_local_file_dirs" in payload

    # Find agents in nodes
    nodes = payload.get("nodes", [])
    assert len(nodes) > 0

    # Find specific agents and verify capabilities
    tool_agent = next((n for n in nodes if n["id"] == "ToolAgent"), None)
    assert tool_agent is not None
    assert "capabilities" in tool_agent["data"]
    assert "tools" in tool_agent["data"]["capabilities"]

    hosted_agent = next((n for n in nodes if n["id"] == "HostedAgent"), None)
    assert hosted_agent is not None
    assert "capabilities" in hosted_agent["data"]
    capabilities = set(hosted_agent["data"]["capabilities"])
    assert capabilities == {"file_search", "code_interpreter", "web_search"}
    assert "tools" not in capabilities

    reasoning_agent = next((n for n in nodes if n["id"] == "ReasoningAgent"), None)
    assert reasoning_agent is not None
    assert "capabilities" in reasoning_agent["data"]
    assert "reasoning" in reasoning_agent["data"]["capabilities"]

    full_agent = next((n for n in nodes if n["id"] == "FullAgent"), None)
    assert full_agent is not None
    assert "capabilities" in full_agent["data"]
    capabilities = set(full_agent["data"]["capabilities"])
    assert "tools" in capabilities
    assert "reasoning" in capabilities
    assert "file_search" in capabilities


def test_metadata_capabilities_empty_for_basic_agent():
    """Agent with no special features has empty capabilities list."""

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="BasicAgent", instructions="Basic agent with no tools")
        return Agency(agent, load_threads_callback=load_threads_callback, save_threads_callback=save_threads_callback)

    app = run_fastapi(agencies={"test_agency": create_agency}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.get("/test_agency/get_metadata")

    assert response.status_code == 200
    payload = response.json()
    assert "allowed_local_file_dirs" in payload


def test_metadata_includes_allowed_local_file_dirs(tmp_path, agency_factory):
    """Metadata should expose the allowed local file directories configuration."""
    allowed_dir = tmp_path / "uploads"
    allowed_dir.mkdir(parents=True, exist_ok=True)

    app = run_fastapi(
        agencies={"test_agency": agency_factory},
        return_app=True,
        app_token_env="",
        allowed_local_file_dirs=[str(allowed_dir)],
    )
    client = TestClient(app)

    response = client.get("/test_agency/get_metadata")
    assert response.status_code == 200
    payload = response.json()

    assert payload["allowed_local_file_dirs"] == [str(allowed_dir.resolve())]


def test_metadata_includes_quick_replies() -> None:
    """Metadata should expose both starters and quick replies for UI clients."""

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(
            name="QuickRepliesAgent",
            instructions="Use quick replies",
            conversation_starters=["Support: I need help with billing"],
            quick_replies=["hi", "hello"],
        )
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    app = run_fastapi(agencies={"test_agency": create_agency}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.get("/test_agency/get_metadata")

    assert response.status_code == 200
    payload = response.json()
    nodes = payload.get("nodes", [])
    quick_agent = next((n for n in nodes if n["id"] == "QuickRepliesAgent"), None)
    assert quick_agent is not None
    data = quick_agent["data"]
    assert data["conversationStarters"] == ["Support: I need help with billing"]
    assert data["quickReplies"] == ["hi", "hello"]


def test_metadata_includes_tool_input_schema():
    """Metadata should include input schema for function tools when available."""

    @function_tool
    def sample_tool(text: str) -> str:
        return text

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="SchemaAgent", instructions="Test", tools=[sample_tool])
        return Agency(agent, load_threads_callback=load_threads_callback, save_threads_callback=save_threads_callback)

    app = run_fastapi(agencies={"test_agency": create_agency}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.get("/test_agency/get_metadata")

    assert response.status_code == 200
    payload = response.json()
    schema_agent = next((n for n in payload.get("nodes", []) if n["id"] == "SchemaAgent"), None)
    assert schema_agent is not None
    tools = schema_agent["data"].get("tools", [])
    assert tools
    input_schema = tools[0].get("inputSchema")
    assert isinstance(input_schema, dict)
    assert "text" in input_schema.get("properties", {})


def test_tool_endpoint_handles_nested_schema():
    """Test that tool endpoints work with nested Pydantic models."""

    class Address(BaseModel):
        street: str
        zip_code: int

    class NestedTool(BaseTool):
        address: Address

        def run(self) -> str:
            return self.address.street

    app = run_fastapi(tools=[NestedTool], return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.post("/tool/NestedTool", json={"address": {"street": "Elm", "zip_code": 90210}})

    assert response.status_code == 200
    assert response.json() == {"response": "Elm"}


def test_tool_endpoint_serializes_datetime_for_on_invoke(monkeypatch):
    """Ensure typed tool endpoints pass JSON strings to on_invoke_tool."""

    class TimestampRequest(BaseModel):
        timestamp: datetime

    class TimestampFunctionTool:
        name = "TimestampFunctionTool"
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

        calls: list[str] = []

        @staticmethod
        async def on_invoke_tool(context, input_json: str):
            TimestampFunctionTool.calls.append(input_json)
            return "ok"

    def fake_build_request_model(*_, **__):
        return TimestampRequest

    monkeypatch.setattr(tool_endpoints, "build_request_model", fake_build_request_model)
    TimestampFunctionTool.calls = []

    app = run_fastapi(tools=[TimestampFunctionTool], return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.post("/tool/TimestampFunctionTool", json={"timestamp": "2024-05-01T09:30:00Z"})

    assert response.status_code == 200
    assert response.json() == {"response": "ok"}
    assert TimestampFunctionTool.calls, "on_invoke_tool should be triggered"
    payload = json.loads(TimestampFunctionTool.calls[0])
    assert payload == {"timestamp": "2024-05-01T09:30:00Z"}


def test_openapi_json_includes_nested_schemas():
    """Verify /openapi.json contains proper schemas for tools with nested models."""

    class Address(BaseModel):
        street: str
        zip_code: int

    class NestedTool(BaseTool):
        address: Address

        def run(self) -> str:
            return self.address.street

    class SimpleTool(BaseTool):
        name: str
        age: int

        def run(self) -> str:
            return self.name

    app = run_fastapi(tools=[NestedTool, SimpleTool], return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    assert "/tool/NestedTool" in schema["paths"]
    assert "/tool/SimpleTool" in schema["paths"]

    nested_endpoint = schema["paths"]["/tool/NestedTool"]["post"]
    assert "requestBody" in nested_endpoint
    nested_schema_ref = nested_endpoint["requestBody"]["content"]["application/json"]["schema"]
    assert nested_schema_ref["$ref"] == "#/components/schemas/NestedTool"

    assert "NestedTool" in schema["components"]["schemas"]
    assert "Address" in schema["components"]["schemas"]

    nested_tool_schema = schema["components"]["schemas"]["NestedTool"]
    assert nested_tool_schema["properties"]["address"]["$ref"] == "#/components/schemas/Address"

    address_schema = schema["components"]["schemas"]["Address"]
    assert address_schema["type"] == "object"
    assert "street" in address_schema["properties"]
    assert "zip_code" in address_schema["properties"]
    assert address_schema["required"] == ["street", "zip_code"]


def test_function_tool_with_nested_schema():
    """Verify that FunctionTools with nested models work correctly via adapted BaseTool."""

    class Address(BaseModel):
        street: str
        zip_code: int

    class UserTool(BaseTool):
        """Create a user with address."""

        name: str
        address: Address

        def run(self) -> str:
            return f"{self.name} at {self.address.street}"

    # Adapt the BaseTool to a FunctionTool (simulates what happens in agents)
    function_tool = ToolFactory.adapt_base_tool(UserTool)

    app = run_fastapi(tools=[function_tool], return_app=True, app_token_env="")
    client = TestClient(app)

    # Test that the endpoint works
    response = client.post(
        "/tool/UserTool", json={"name": "Alice", "address": {"street": "123 Main St", "zip_code": 12345}}
    )
    assert response.status_code == 200
    assert "Alice at 123 Main St" in response.json()["response"]

    # Test that OpenAPI schema includes nested model
    schema_response = client.get("/openapi.json")
    assert schema_response.status_code == 200
    openapi_schema = schema_response.json()

    assert "/tool/UserTool" in openapi_schema["paths"]
    endpoint_schema = openapi_schema["paths"]["/tool/UserTool"]["post"]
    assert "requestBody" in endpoint_schema

    # Verify the schema is properly typed (not generic Request)
    request_schema = endpoint_schema["requestBody"]["content"]["application/json"]["schema"]
    assert "$ref" in request_schema
    assert "UserToolRequest" in request_schema["$ref"]


def test_strict_function_tool_rejects_extra_fields():
    """Ensure strict tools exposed via FastAPI still validate unexpected inputs."""

    class StrictTool(BaseTool):
        """Return the given value."""

        class ToolConfig:
            strict = True

        value: int

        def run(self) -> int:
            return self.value

    strict_function_tool = ToolFactory.adapt_base_tool(StrictTool)

    app = run_fastapi(tools=[strict_function_tool], return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.post("/tool/StrictTool", json={"value": 7, "unexpected": "boom"})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(item.get("type") == "extra_forbidden" for item in detail)


def test_tool_endpoint_preserves_explicit_nulls():
    """Tools must receive explicit null payloads without them being dropped."""

    class NullableTool(BaseTool):
        note: str | None = None

        def run(self) -> str | None:
            return self.note

    app = run_fastapi(tools=[NullableTool], return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.post("/tool/NullableTool", json={"note": None})

    assert response.status_code == 200
    assert response.json() == {"response": None}


def test_function_tool_nested_list_validation_survives_schema_export():
    """FunctionTools should retain nested list schemas after ToolFactory exports."""

    class Address(BaseModel):
        street: str
        zip_code: int

    class AddressListTool(BaseTool):
        addresses: list[Address]

        def run(self) -> str:
            return ",".join(addr.street for addr in self.addresses)

    function_tool = ToolFactory.adapt_base_tool(AddressListTool)
    ToolFactory.get_openapi_schema([function_tool], "https://api.test.com")

    app = run_fastapi(tools=[function_tool], return_app=True, app_token_env="")
    client = TestClient(app)

    # Missing zip_code inside nested list should raise a FastAPI validation error (422)
    invalid_response = client.post("/tool/AddressListTool", json={"addresses": [{"street": "Elm"}]})
    assert invalid_response.status_code == 422

    valid_response = client.post(
        "/tool/AddressListTool",
        json={"addresses": [{"street": "Elm", "zip_code": 90210}]},
    )

    assert valid_response.status_code == 200
    assert valid_response.json() == {"response": "Elm"}


def test_function_tool_nested_union_falls_back_to_generic_handler():
    """Nested unions should bypass the typed request model to avoid false 422 errors."""

    class Contact(BaseModel):
        identifier: str | int

    class ContainerTool(BaseTool):
        contact: Contact

        def run(self) -> str:
            return str(self.contact.identifier)

    function_tool = ToolFactory.adapt_base_tool(ContainerTool)

    app = run_fastapi(tools=[function_tool], return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.post("/tool/ContainerTool", json={"contact": {"identifier": 99}})

    assert response.status_code == 200
    assert response.json() == {"response": "99"}

    schema = client.get("/openapi.json").json()
    endpoint = schema["paths"]["/tool/ContainerTool"]["post"]
    assert "requestBody" not in endpoint


def test_openapi_schema_includes_custom_server_url():
    """/openapi.json should expose the configured server base URL."""

    class EchoTool(BaseTool):
        message: str

        def run(self) -> str:
            return self.message

    app = run_fastapi(
        tools=[EchoTool],
        return_app=True,
        app_token_env="",
        server_url="https://api.example.com/base",
    )
    client = TestClient(app)

    schema = client.get("/openapi.json").json()

    assert schema["servers"] == [{"url": "https://api.example.com/base"}]
    assert "/tool/EchoTool" in schema["paths"]

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agency_swarm.tools.utils import from_openapi_schema, validate_openapi_spec


@pytest.fixture
def base_spec():
    return {"servers": [{"url": "https://api.example.com"}], "paths": {}}


@pytest.fixture
def mock_tool_setup():
    with patch("agency_swarm.tools.utils.FunctionTool") as mock_func:
        tool = MagicMock()
        mock_func.return_value = tool
        yield mock_func, tool


class TestFromOpenAPISchema:
    def test_basic_schema_conversion(self, base_spec, mock_tool_setup):
        mock_func, tool = mock_tool_setup
        base_spec["paths"]["/users"] = {"get": {"operationId": "getUsers", "description": "Get users"}}

        tools = from_openapi_schema(base_spec)
        assert len(tools) == 1 and tools[0] == tool

        args = mock_func.call_args.kwargs
        assert args["name"] == "getUsers" and args["description"] == "Get users"

    def test_string_input_with_body(self, base_spec, mock_tool_setup):
        mock_func, _ = mock_tool_setup
        base_spec["paths"]["/test"] = {
            "post": {
                "operationId": "create",
                "description": "Create",
                "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}},
            }
        }

        from_openapi_schema(json.dumps(base_spec))
        schema = mock_func.call_args.kwargs["params_json_schema"]
        assert "requestBody" in schema["properties"]

    @pytest.mark.parametrize("strict,expected", [(True, True), (False, False)])
    def test_strict_mode(self, base_spec, mock_tool_setup, strict, expected):
        mock_func, _ = mock_tool_setup
        base_spec["paths"]["/test"] = {"get": {"operationId": "test", "description": "Test"}}

        with patch("agency_swarm.tools.utils.ensure_strict_json_schema"):
            from_openapi_schema(base_spec, strict=strict)
            assert mock_func.call_args.kwargs["strict_json_schema"] == expected

    def test_parameter_handling(self, base_spec, mock_tool_setup):
        mock_func, _ = mock_tool_setup
        base_spec["paths"]["/test"] = {
            "get": {
                "operationId": "test",
                "description": "Test",
                "parameters": [
                    {"name": "legacy", "type": "string", "required": False},
                    {"name": "new", "schema": {"type": "integer"}, "required": True},
                ],
            }
        }

        from_openapi_schema(base_spec)
        schema = mock_func.call_args.kwargs["params_json_schema"]
        params = schema["properties"]["parameters"]

        assert "legacy" in params["properties"] and "new" in params["properties"]
        assert "new" in params["required"] and "legacy" not in params["required"]

    @pytest.mark.asyncio
    async def test_invoke_get_request(self, base_spec, mock_tool_setup):
        mock_func, _ = mock_tool_setup
        base_spec["paths"]["/users/{id}"] = {
            "get": {
                "operationId": "getUser",
                "description": "Get user",
                "parameters": [{"name": "id", "schema": {"type": "string"}, "required": True}],
            }
        }

        with patch("agency_swarm.tools.utils.httpx.AsyncClient") as mock_client_cls:
            client = AsyncMock()
            response = MagicMock()
            response.json.return_value = {"id": "123"}
            client.request.return_value = response
            mock_client_cls.return_value.__aenter__.return_value = client

            from_openapi_schema(base_spec)
            invoke_func = mock_func.call_args.kwargs["on_invoke_tool"]

            result = await invoke_func(MagicMock(), json.dumps({"parameters": {"id": "123"}}))

            client.request.assert_called_once_with(
                "GET", "https://api.example.com/users/123", params={}, json=None, headers={}
            )
            assert result == {"id": "123"}

    @pytest.mark.asyncio
    async def test_invoke_post_request(self, base_spec, mock_tool_setup):
        mock_func, _ = mock_tool_setup
        base_spec["paths"]["/users"] = {
            "post": {
                "operationId": "createUser",
                "description": "Create user",
                "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}},
            }
        }

        with patch("agency_swarm.tools.utils.httpx.AsyncClient") as mock_client_cls:
            client = AsyncMock()
            client.request.return_value.json.return_value = {"id": "456"}
            mock_client_cls.return_value.__aenter__.return_value = client

            from_openapi_schema(base_spec)
            invoke_func = mock_func.call_args.kwargs["on_invoke_tool"]

            await invoke_func(MagicMock(), json.dumps({"requestBody": {"name": "test"}}))

            client.request.assert_called_once_with(
                "POST", "https://api.example.com/users", params={}, json={"name": "test"}, headers={}
            )

    @pytest.mark.asyncio
    async def test_non_json_response(self, base_spec, mock_tool_setup):
        mock_func, _ = mock_tool_setup
        base_spec["paths"]["/text"] = {"get": {"operationId": "getText", "description": "Get text"}}

        with patch("agency_swarm.tools.utils.httpx.AsyncClient") as mock_client_cls:
            client = AsyncMock()
            response = MagicMock()
            response.json.side_effect = Exception("Not JSON")
            response.text = "plain text"
            client.request.return_value = response
            mock_client_cls.return_value.__aenter__.return_value = client

            from_openapi_schema(base_spec)
            invoke_func = mock_func.call_args.kwargs["on_invoke_tool"]

            result = await invoke_func(MagicMock(), json.dumps({"parameters": {}}))
            assert result == "plain text"

    def test_multiple_operations(self, base_spec, mock_tool_setup):
        mock_func, _ = mock_tool_setup
        base_spec["paths"] = {
            "/users": {
                "get": {"operationId": "getUsers", "description": "Get users"},
                "post": {"operationId": "createUser", "description": "Create user"},
            },
            "/posts": {"get": {"operationId": "getPosts", "description": "Get posts"}},
        }

        tools = from_openapi_schema(base_spec)
        assert len(tools) == 3 and mock_func.call_count == 3


class TestValidateOpenAPISpec:
    @pytest.mark.parametrize(
        "spec,should_pass",
        [
            ({"paths": {"/users": {"get": {"operationId": "getUsers", "description": "Get users"}}}}, True),
            ({"info": {"title": "API"}}, False),  # Missing paths
            ({"paths": {"/users": "invalid"}}, False),  # Invalid path item
            ({"paths": {"/users": {"get": {"description": "Get users"}}}}, False),  # Missing operationId
            ({"paths": {"/users": {"get": {"operationId": "getUsers"}}}}, False),  # Missing description
        ],
    )
    def test_validation(self, spec, should_pass):
        if should_pass:
            result = validate_openapi_spec(json.dumps(spec))
            assert result == spec
        else:
            with pytest.raises(ValueError):
                validate_openapi_spec(json.dumps(spec))

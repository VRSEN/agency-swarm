"""
Unit tests for ToolFactory OpenAPI and schema functionality.

Tests the OpenAPI schema conversion and HTTP callback functionality with real data.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents import FunctionTool
from agents.exceptions import ModelBehaviorError
from pydantic import ValidationError

from agency_swarm.tools.base_tool import BaseTool
from agency_swarm.tools.tool_factory import ToolFactory


class TestFromOpenaiSchema:
    """Test OpenAI schema conversion with real schemas."""

    def test_extracts_parameters_model(self):
        """Test extraction of parameters model from schema."""
        schema = {
            "properties": {
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
                    "required": ["query"],
                }
            }
        }

        param_model, request_body_model = ToolFactory.from_openai_schema(schema, "test_function")

        # Test real behavior - should generate actual model
        assert param_model is not None
        assert request_body_model is None

        # Test the model actually works
        instance = param_model(query="test", limit=5)
        assert instance.query == "test"
        assert instance.limit == 5

        # Test validation
        with pytest.raises(ValidationError):
            param_model(limit=5)  # Missing required 'query'

    def test_extracts_request_body_model(self):
        """Test extraction of request body model from schema."""
        schema = {"properties": {"requestBody": {"type": "object", "properties": {"data": {"type": "string"}}}}}

        param_model, request_body_model = ToolFactory.from_openai_schema(schema, "test_function")

        # Test real behavior
        assert param_model is None
        assert request_body_model is not None

        # Test the model works
        instance = request_body_model(data="test content")
        assert instance.data == "test content"

    def test_handles_empty_schema(self):
        """Test handling of schema with no parameters or request body."""
        schema = {"properties": {}}

        param_model, request_body_model = ToolFactory.from_openai_schema(schema, "empty_function")

        assert param_model is None
        assert request_body_model is None

    def test_handles_strict_mode(self):
        """Test handling of strict mode in schema."""
        schema = {
            "strict": True,
            "properties": {"parameters": {"type": "object", "properties": {"field": {"type": "string"}}}},
        }

        param_model, request_body_model = ToolFactory.from_openai_schema(schema, "strict_function")

        # Test that model is generated and works
        assert param_model is not None
        assert request_body_model is None

        # Test the model works with strict mode
        instance = param_model(field="test")
        assert instance.field == "test"


class TestFromOpenapiSchema:
    """Test OpenAPI schema conversion with real schemas."""

    def test_converts_simple_openapi_schema(self):
        """Test conversion of a simple OpenAPI schema."""
        openapi_schema = {
            "paths": {
                "/test": {
                    "post": {
                        "operationId": "test_operation",
                        "description": "Test operation",
                        "parameters": [
                            {"name": "query", "in": "query", "schema": {"type": "string"}, "required": True}
                        ],
                    }
                }
            }
        }

        result = ToolFactory.from_openapi_schema(openapi_schema)

        assert len(result) == 1
        tool = result[0]
        assert isinstance(tool, FunctionTool)
        assert tool.name == "test_operation"
        assert "test operation" in tool.description.lower()

    def test_converts_json_string_schema(self):
        """Test conversion of OpenAPI schema as JSON string."""
        openapi_schema = {"paths": {"/test": {"get": {"operationId": "get_test", "summary": "Get test data"}}}}

        json_string = json.dumps(openapi_schema)
        result = ToolFactory.from_openapi_schema(json_string)

        assert len(result) == 1
        assert result[0].name == "get_test"

    def test_handles_request_body(self):
        """Test handling of request body in OpenAPI schema."""
        openapi_schema = {
            "paths": {
                "/test": {
                    "post": {
                        "operationId": "post_test",
                        "description": "Post test data",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object", "properties": {"data": {"type": "string"}}}
                                }
                            }
                        },
                    }
                }
            }
        }

        result = ToolFactory.from_openapi_schema(openapi_schema)

        assert len(result) == 1
        tool = result[0]
        assert tool.name == "post_test"
        # Verify schema includes request body handling
        assert "properties" in tool.params_json_schema

    def test_applies_strict_mode(self):
        """Test application of strict mode to schemas."""
        openapi_schema = {
            "paths": {
                "/test": {
                    "post": {
                        "operationId": "strict_test",
                        "description": "Strict test",
                        "parameters": [{"name": "field", "in": "query", "schema": {"type": "string"}}],
                    }
                }
            }
        }

        result = ToolFactory.from_openapi_schema(openapi_schema, strict=True)

        assert len(result) == 1
        tool = result[0]
        assert tool.strict_json_schema is True

    def test_filters_none_headers(self):
        """Test that None headers are filtered out."""
        openapi_schema = {"paths": {"/test": {"get": {"operationId": "header_test", "description": "Header test"}}}}

        headers = {"Authorization": "Bearer token", "X-Custom": None, "Content-Type": "application/json"}

        # Should not raise error and should filter None values
        result = ToolFactory.from_openapi_schema(openapi_schema, headers=headers)

        assert len(result) == 1
        # The actual header filtering is tested in the HTTP execution tests


class TestCreateInvokeForPath:
    """Test HTTP invoke callback creation. HTTP mocks ARE needed here since we can't make real HTTP calls."""

    @pytest.mark.asyncio
    async def test_successful_http_call(self):
        """Test successful HTTP request execution."""
        openapi = {"servers": [{"url": "https://api.example.com"}]}
        tool_schema = {
            "properties": {
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
            }
        }

        # HTTP mocking IS justified - we can't make real external HTTP calls in tests
        with patch("agency_swarm.tools.tool_factory.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"result": "success"}
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(return_value=mock_response)

            callback = ToolFactory._create_invoke_for_path("/test", "GET", openapi, tool_schema, "test_func")

            result = await callback(None, '{"parameters": {"query": "test"}}')

            assert result == {"result": "success"}

    @pytest.mark.asyncio
    async def test_path_parameter_substitution(self):
        """Test substitution of path parameters in URL."""
        openapi = {"servers": [{"url": "https://api.example.com"}]}
        tool_schema = {
            "properties": {
                "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}
            }
        }

        # HTTP mocking IS justified here
        with patch("agency_swarm.tools.tool_factory.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"result": "found"}
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(return_value=mock_response)

            callback = ToolFactory._create_invoke_for_path("/users/{id}", "GET", openapi, tool_schema, "get_user")

            await callback(None, '{"parameters": {"id": "123"}}')

            # Verify URL substitution actually happened
            request_call = mock_client.return_value.__aenter__.return_value.request
            call_args = request_call.call_args
            assert "https://api.example.com/users/123" in call_args[0]

    @pytest.mark.asyncio
    async def test_json_body_for_post_methods(self):
        """Test that JSON body is sent for POST/PUT/PATCH methods."""
        openapi = {"servers": [{"url": "https://api.example.com"}]}
        tool_schema = {"properties": {"requestBody": {"type": "object", "properties": {"data": {"type": "string"}}}}}

        # HTTP mocking IS justified
        with patch("agency_swarm.tools.tool_factory.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"created": True}
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(return_value=mock_response)

            callback = ToolFactory._create_invoke_for_path("/test", "POST", openapi, tool_schema, "create_test")

            await callback(None, '{"requestBody": {"data": "test"}}')

            # Verify JSON body was sent - this is the real behavior we care about
            request_call = mock_client.return_value.__aenter__.return_value.request
            call_kwargs = request_call.call_args[1]
            assert call_kwargs["json"] == {"data": "test"}

    @pytest.mark.asyncio
    async def test_response_text_fallback(self):
        """Test fallback to text response when JSON parsing fails."""
        openapi = {"servers": [{"url": "https://api.example.com"}]}
        tool_schema = {"properties": {}}

        # HTTP mocking IS justified
        with patch("agency_swarm.tools.tool_factory.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.side_effect = Exception("Not JSON")
            mock_response.text = "Plain text response"
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(return_value=mock_response)

            callback = ToolFactory._create_invoke_for_path("/test", "GET", openapi, tool_schema, "text_func")

            result = await callback(None, "{}")

            assert result == "Plain text response"

    @pytest.mark.asyncio
    async def test_validation_error_handling(self):
        """Test handling of validation errors in parameters."""
        tool_schema = {
            "properties": {
                "parameters": {
                    "type": "object",
                    "properties": {"required_field": {"type": "string"}},
                    "required": ["required_field"],
                }
            }
        }

        # Provide minimal OpenAPI metadata so the invoke path builds a proper URL
        openapi = {"servers": [{"url": "https://api.example.com"}]}
        callback = ToolFactory._create_invoke_for_path("/test", "POST", openapi, tool_schema, "test_func")

        # Test real validation error with missing required field
        with pytest.raises(ModelBehaviorError, match="Invalid JSON input in parameters"):
            await callback(None, '{"parameters": {}}')  # Missing required_field


class TestGetOpenapiSchema:
    """Test OpenAPI schema generation with real tools."""

    def test_generates_schema_for_base_tools(self):
        """Test schema generation for BaseTool classes."""

        class TestBaseTool(BaseTool):
            """Test tool for schema generation."""

            input_field: str

            def run(self):
                return f"result: {self.input_field}"

        result_json = ToolFactory.get_openapi_schema([TestBaseTool], "https://api.test.com")
        result = json.loads(result_json)

        assert result["info"]["title"] == "Agent Tools"
        assert "/TestBaseTool" in result["paths"]
        assert result["paths"]["/TestBaseTool"]["post"]["operationId"] == "TestBaseTool"

        # Verify the schema includes the input field
        request_body = result["paths"]["/TestBaseTool"]["post"]["requestBody"]
        assert "content" in request_body

    def test_generates_schema_for_function_tools(self):
        """Test schema generation for FunctionTool instances - using real tool from tests."""
        from tests.data.tools.sample_tool import sample_tool

        result_json = ToolFactory.get_openapi_schema([sample_tool], "https://api.test.com")
        result = json.loads(result_json)

        assert "/sample_tool" in result["paths"]
        assert result["paths"]["/sample_tool"]["post"]["operationId"] == "sample_tool"

    def test_handles_custom_title_and_description(self):
        """Test custom title and description in schema generation."""

        class SimpleTestTool(BaseTool):
            def run(self):
                return "test"

        result_json = ToolFactory.get_openapi_schema(
            [SimpleTestTool], "https://api.test.com", title="Custom API", description="Custom description"
        )
        result = json.loads(result_json)

        assert result["info"]["title"] == "Custom API"
        assert result["info"]["description"] == "Custom description"

    def test_raises_error_for_invalid_tool_type(self):
        """Test error handling for unsupported tool types."""
        invalid_tool = "not a tool"

        with pytest.raises(TypeError, match="Tool .* is not a BaseTool or FunctionTool"):
            ToolFactory.get_openapi_schema([invalid_tool], "https://api.test.com")

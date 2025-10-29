import json

import pytest
from agents import FunctionTool
from agents.exceptions import ModelBehaviorError

from agency_swarm.tools.base_tool import BaseTool
from agency_swarm.tools.tool_factory import ToolFactory


class TestFromOpenapiSchema:
    def test_converts_simple_openapi_schema(self):
        schema = {
            "openapi": "3.1.0",
            "servers": [{"url": "https://api.test.com"}],
            "paths": {
                "/tickets": {
                    "post": {
                        "operationId": "create_ticket",
                        "description": "Create a support ticket",
                        "parameters": [
                            {
                                "name": "priority",
                                "in": "query",
                                "schema": {"type": "string"},
                                "required": False,
                            }
                        ],
                    }
                }
            },
        }

        tools = ToolFactory.from_openapi_schema(schema, strict=False)

        assert len(tools) == 1
        tool = tools[0]
        assert isinstance(tool, FunctionTool)
        assert tool.name == "create_ticket"
        assert "support ticket" in tool.description.lower()

    @pytest.mark.asyncio
    async def test_validation_errors_raise_model_behavior_error(self):
        schema = {
            "openapi": "3.1.0",
            "servers": [{"url": "https://api.test.com"}],
            "paths": {
                "/tickets": {
                    "post": {
                        "operationId": "create_ticket",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"message": {"type": "string"}},
                                        "required": ["message"],
                                    }
                                }
                            },
                        },
                    }
                }
            },
        }

        tools = ToolFactory.from_openapi_schema(schema, strict=False)
        tool = tools[0]

        with pytest.raises(ModelBehaviorError, match="Invalid JSON input in request body"):
            await tool.on_invoke_tool(None, json.dumps({"requestBody": {}}))


class TestGetOpenapiSchema:
    def test_generates_schema_for_base_tools(self):
        class TestTool(BaseTool):
            input_field: str

            def run(self):
                return self.input_field

        result_json = ToolFactory.get_openapi_schema([TestTool], "https://api.test.com")
        result = json.loads(result_json)

        assert result["info"]["title"] == "Agent Tools"
        assert "/TestTool" in result["paths"]
        assert result["paths"]["/TestTool"]["post"]["operationId"] == "TestTool"

    def test_generates_schema_for_function_tool(self):
        async def dummy_tool(ctx, input_json: str):
            return "ok"

        function_tool = FunctionTool(
            name="dummy_tool",
            description="Dummy tool",
            params_json_schema={"type": "object", "properties": {}},
            on_invoke_tool=dummy_tool,
        )

        result_json = ToolFactory.get_openapi_schema([function_tool], "https://api.test.com")
        result = json.loads(result_json)

        assert "/dummy_tool" in result["paths"]
        assert result["paths"]["/dummy_tool"]["post"]["operationId"] == "dummy_tool"

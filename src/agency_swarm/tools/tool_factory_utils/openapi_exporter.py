from __future__ import annotations

import inspect
import json
import logging
from copy import deepcopy
from typing import Any

from agents import FunctionTool

from agency_swarm.tools.base_tool import BaseTool

from .schema_inspector import supports_request_model

logger = logging.getLogger(__name__)


def get_openapi_schema(
    tools: list[type[BaseTool] | FunctionTool],
    url: str,
    title: str = "Agent Tools",
    description: str = "A collection of tools.",
) -> str:
    """
    Generates an OpenAPI schema from a list of BaseTools or FunctionTools.
    """
    schema: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": title, "description": description, "version": "v1.0.0"},
        "servers": [{"url": url}],
        "paths": {},
        "components": {
            "schemas": {},
            "securitySchemes": {"HTTPBearer": {"type": "http", "scheme": "bearer"}},
        },
    }

    for tool in tools:
        if inspect.isclass(tool) and issubclass(tool, BaseTool):
            openai_schema = tool.openai_schema
            parameters_schema = deepcopy(openai_schema["parameters"])
            logger.debug("OpenAPI schema for %s: %s", tool.__name__, openai_schema)
        elif isinstance(tool, FunctionTool):
            parameters_schema = deepcopy(tool.params_json_schema)
            openai_schema = {
                "parameters": parameters_schema,
                "name": tool.name,
                "description": getattr(tool, "description", ""),
            }
            logger.debug("OpenAPI schema for %s: %s", tool.name, openai_schema)
        else:
            raise TypeError(f"Tool {tool} is not a BaseTool or FunctionTool.")

        request_model_supported = supports_request_model(parameters_schema)
        defs = parameters_schema.get("$defs", {})

        if request_model_supported:
            request_schema = deepcopy(parameters_schema)
            request_schema.pop("$defs", None)
            request_schema.setdefault("type", "object")
            request_schema.setdefault("title", openai_schema["name"])
            if "description" not in request_schema and "description" in openai_schema:
                request_schema["description"] = openai_schema["description"]
            schema["components"]["schemas"][openai_schema["name"]] = request_schema

        summary = openai_schema["name"].replace("_", " ").title()
        responses: dict[str, Any] = {
            "200": {
                "description": "Tool executed successfully",
                "content": {"application/json": {"schema": {}}},
            }
        }

        post_entry: dict[str, Any] = {
            "summary": summary,
            "operationId": openai_schema["name"],
            "responses": responses,
            "security": [{"HTTPBearer": []}],
        }

        if request_model_supported:
            _ensure_validation_components(schema)
            responses["422"] = {
                "description": "Validation Error",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/HTTPValidationError"}}},
            }
            post_entry["requestBody"] = {
                "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{openai_schema['name']}"}}},
                "required": True,
            }
            if isinstance(defs, dict):
                schema["components"]["schemas"].update(defs)

        schema["paths"][f"/tool/{openai_schema['name']}"] = {"post": post_entry}

    schema_str = json.dumps(schema, indent=2).replace("#/$defs/", "#/components/schemas/")
    return schema_str


def _ensure_validation_components(schema: dict[str, Any]) -> None:
    components = schema.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    if "ValidationError" not in schemas:
        schemas["ValidationError"] = {
            "title": "ValidationError",
            "type": "object",
            "properties": {
                "loc": {
                    "title": "Location",
                    "type": "array",
                    "items": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
                },
                "msg": {"title": "Message", "type": "string"},
                "type": {"title": "Error Type", "type": "string"},
            },
            "required": ["loc", "msg", "type"],
        }
    if "HTTPValidationError" not in schemas:
        schemas["HTTPValidationError"] = {
            "title": "HTTPValidationError",
            "type": "object",
            "properties": {
                "detail": {
                    "title": "Detail",
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/ValidationError"},
                }
            },
        }

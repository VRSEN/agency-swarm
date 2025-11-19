from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import jsonref
from agents import FunctionTool
from agents.exceptions import ModelBehaviorError
from agents.run_context import RunContextWrapper
from pydantic import BaseModel, ValidationError

from agency_swarm.tools.utils import (
    build_parameter_object_schema,
    build_tool_schema,
    generate_model_from_schema,
    resolve_url,
)

logger = logging.getLogger(__name__)


def from_openai_schema(
    schema: dict[str, Any], function_name: str
) -> tuple[type[BaseModel] | None, type[BaseModel] | None]:
    """
    Converts an OpenAI schema into Pydantic models for parameters and request body.
    """
    param_model: type[BaseModel] | None = None
    request_body_model: type[BaseModel] | None = None
    strict = schema.get("strict", False)
    camel_func_name = "".join(word.capitalize() for word in function_name.replace("_", " ").split())

    if "parameters" in schema["properties"] and schema["properties"]["parameters"]:
        param_model = generate_model_from_schema(schema["properties"]["parameters"], camel_func_name, strict)

    request_body_schema = schema.get("properties", {}).get("requestBody", {})
    if request_body_schema:
        request_body_model = generate_model_from_schema(request_body_schema, camel_func_name, strict)

    return param_model, request_body_model


def from_openapi_schema(
    schema: str | dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    strict: bool = False,
    timeout: int = 90,
) -> list[FunctionTool]:
    """
    Converts an OpenAPI spec describing a single endpoint into FunctionTool instances.
    """
    if isinstance(schema, dict):
        openapi = jsonref.JsonRef.replace_refs(schema)
    else:
        openapi = jsonref.loads(schema)

    headers = {k: v for k, v in (headers or {}).items() if v is not None}
    tools: list[FunctionTool] = []

    for path, verbs in openapi["paths"].items():
        for verb, verb_spec_ref in verbs.items():
            verb_spec = jsonref.replace_refs(verb_spec_ref)

            function_name = verb_spec.get("operationId")
            description = verb_spec.get("description") or verb_spec.get("summary", "")

            req_body_schema = None
            if content := verb_spec.get("requestBody", {}).get("content", {}):
                for content_obj in content.values():
                    if "schema" in content_obj:
                        req_body_schema = content_obj["schema"]
                        break

            parameters_obj_schema = build_parameter_object_schema(verb_spec.get("parameters", []), strict)
            tool_schema = build_tool_schema(
                parameters_obj_schema, req_body_schema, strict=strict, include_strict_flag=True
            )
            tool_schema["strict"] = strict

            on_invoke_tool = _create_invoke_for_path(
                path, verb, openapi, tool_schema, function_name, headers, params, timeout
            )

            tool = FunctionTool(
                name=function_name,
                description=description,
                params_json_schema=tool_schema,
                on_invoke_tool=on_invoke_tool,
                strict_json_schema=strict,
            )
            tools.append(tool)

    return tools


def _create_invoke_for_path(path, verb, openapi, tool_schema, function_name, headers=None, params=None, timeout=90):
    """
    Factory that captures HTTP request details and returns the FunctionTool callback.
    """
    param_model, request_body_model = from_openai_schema(tool_schema, function_name)
    fixed_params = params or {}

    async def _invoke(
        ctx: RunContextWrapper[Any],
        input: str,
        *,
        verb_: str = verb,
        path_: str = path,
        param_model_: type[BaseModel] | None = param_model,
        request_body_model_: type[BaseModel] | None = request_body_model,
    ):
        payload = json.loads(input) if input else {}

        param_container: dict[str, Any] = payload.get("parameters", {})
        if param_model_:
            try:
                parsed = param_model_(**param_container) if param_container else param_model_()
                param_container = parsed.model_dump(mode="json")
            except ValidationError as e:
                raise ModelBehaviorError(
                    f"Invalid JSON input in parameters for tool {param_model_.__name__}: {e}"
                ) from e

        body_payload = payload.get("requestBody")
        if request_body_model_:
            try:
                parsed = request_body_model_(**body_payload) if body_payload else request_body_model_()
                body_payload = parsed.model_dump(mode="json")
            except ValidationError as e:
                raise ModelBehaviorError(
                    f"Invalid JSON input in request body for tool {request_body_model_.__name__}: {e}"
                ) from e

        url, remaining_params = resolve_url(openapi["servers"][0]["url"], path_, param_container)
        query_params = {k: v for k, v in remaining_params.items() if v is not None}
        if fixed_params:
            query_params = {**query_params, **fixed_params}

        json_body = body_payload if verb_.lower() in {"post", "put", "patch", "delete"} else None
        logger.info("Calling URL: %s\nQuery Params: %s\nJSON Body: %s", url, query_params, json_body)

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(
                verb_.upper(),
                url,
                params=query_params,
                json=json_body,
                headers=headers,
            )
            try:
                logger.info("Response from %s: %s", url, resp.json())
                return resp.json()
            except Exception:  # pragma: no cover - fallback formatting
                return resp.text

    return _invoke

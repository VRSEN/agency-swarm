"""OpenAPI schema conversion utilities."""

import json
import logging
from typing import Any

import httpx
import jsonref
from agents import FunctionTool
from agents.exceptions import ModelBehaviorError
from agents.run_context import RunContextWrapper
from pydantic import BaseModel, ValidationError

from .utils import build_parameter_object_schema, build_tool_schema, generate_model_from_schema, resolve_url

logger = logging.getLogger(__name__)


def from_openai_schema(schema: dict[str, Any], function_name: str) -> tuple[type | None, type | None]:
    """
    Converts an OpenAI schema into Pydantic models for parameters and request body.
    Returns:
        A dict with keys 'parameters' and 'request_body' (if present), each mapping to a Pydantic model.
    """
    param_model = None
    request_body_model = None
    strict = schema.get("strict", False)
    camel_func_name = "".join(word.capitalize() for word in function_name.replace("_", " ").split())

    # Parameters model
    if "parameters" in schema["properties"] and schema["properties"]["parameters"]:
        param_model = generate_model_from_schema(schema["properties"]["parameters"], camel_func_name, strict)

    # Request body model (first schema in any content type)
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
    Converts an OpenAPI JSON or dictionary describing a single endpoint into one or more FunctionTool instances.

    Args:
        schema (str | dict): Full OpenAPI JSON string or dictionary.
        headers (dict[str, str] | None, optional): Extra HTTP headers to send with each call. Defaults to None.
        params (dict[str, Any] | None, optional): Extra query parameters to append to every call. Defaults to None.
        strict (bool, optional): Applies `strict` standard to schema that the OpenAI API expects. Defaults to True.
        timeout (int, optional): HTTP timeout in seconds. Defaults to 90.

    Returns:
        list[FunctionTool]: List of FunctionTool instances generated from the OpenAPI endpoint.
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

            # Build OpenAI-compatible JSON schema

            function_name = verb_spec.get("operationId")
            description = verb_spec.get("description") or verb_spec.get("summary", "")

            req_body_schema = None
            if content := verb_spec.get("requestBody", {}).get("content", {}):
                for content_obj in content.values():
                    if "schema" in content_obj:
                        req_body_schema = content_obj["schema"]
                        break

            parameters_obj_schema = build_parameter_object_schema(
                verb_spec.get("parameters", []),
                strict,
            )

            tool_schema = build_tool_schema(
                parameters_obj_schema,
                req_body_schema,
                strict=strict,
                include_strict_flag=True,
            )
            tool_schema["strict"] = strict

            # Callback factory (captures current verb & path)
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
    Creates a callback function for a specific path and method.
    This is a factory function that captures the current values of path and method.

    Parameters:
        path: The path to create the callback for.
        verb: The HTTP method to use.
        openapi: The OpenAPI specification.
        tool_schema: The schema for the tool.
        function_name: The function/operation name.
        headers: Headers to include in the request.
        params: Additional parameters to include in the request.
        timeout: HTTP timeout in seconds.

    Returns:
        An async callback function that makes the appropriate HTTP request.
    """
    param_model, request_body_model = from_openai_schema(tool_schema, function_name)
    fixed_params = params or {}

    async def _invoke(
        ctx: RunContextWrapper[Any],
        input: str,
        *,
        verb_: str = verb,
        path_: str = path,
        param_model_: type[BaseModel] = param_model,
        request_body_model_: type[BaseModel] = request_body_model,
    ):
        """Actual HTTP call executed by the agent."""
        payload = json.loads(input) if input else {}

        # split out parts for old-style structure
        param_container: dict[str, Any] = payload.get("parameters", {})

        if param_model_:
            # Validate parameters
            try:
                parsed = param_model_(**param_container) if param_container else param_model_()
                param_container = parsed.model_dump(mode="json")
            except ValidationError as e:
                raise ModelBehaviorError(
                    f"Invalid JSON input in parameters for tool {param_model_.__name__}: {e}"
                ) from e

        body_payload = payload.get("requestBody")

        if request_body_model_:
            # Validate request body
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

        logger.info(f"Calling URL: {url}\nQuery Params: {query_params}\nJSON Body: {json_body}")

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(
                verb_.upper(),
                url,
                params=query_params,
                json=json_body,
                headers=headers,
            )
            try:
                logger.info(f"Response from {url}: {resp.json()}")
                return resp.json()
            except Exception:
                return resp.text

    return _invoke


from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import jsonref
from agents import FunctionTool
from agents.run_context import RunContextWrapper
from agents.strict_schema import ensure_strict_json_schema

logger = logging.getLogger(__name__)


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
        strict (bool, optional): If True, sets 'additionalProperties' to False in every generated schema. Defaults to True.
        timeout (int, optional): HTTP timeout in seconds. Defaults to 90.

    Returns:
        list[FunctionTool]: List of FunctionTool instances generated from the OpenAPI endpoint.
    """

    if isinstance(schema, dict):
        openapi = jsonref.JsonRef.replace_refs(schema)
    else:
        openapi = jsonref.loads(schema)

    headers = {k: v for k, v in (headers or {}).items() if v is not None}
    fixed_params = params or {}

    tools: list[FunctionTool] = []

    for path, verbs in openapi["paths"].items():
        for verb, verb_spec_ref in verbs.items():
            verb_spec = jsonref.replace_refs(verb_spec_ref)

            # Build OpenAI-compatible JSON schema

            function_name = verb_spec.get("operationId")
            description = verb_spec.get("description") or verb_spec.get("summary", "")

            req_body_schema = (
                verb_spec.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            )

            param_properties: dict[str, Any] = {}
            required_params: list[str] = []
            for p in verb_spec.get("parameters", []):
                # normalise spec → openapi3 guarantees p["schema"] when parsing
                if "schema" not in p and "type" in p:
                    p["schema"] = {"type": p["type"]}
                param_schema = param_properties.setdefault(p["name"], p["schema"].copy())
                if "description" in p:
                    param_schema["description"] = p["description"]
                if "example" in p:
                    param_schema["example"] = p["example"]
                if "examples" in p:
                    param_schema["examples"] = p["examples"]
                if p.get("required"):
                    required_params.append(p["name"])

            # nested `"parameters"` object for legacy agents
            parameters_obj_schema: dict[str, Any] = {
                "type": "object",
                "properties": param_properties,
                "required": required_params,
                "additionalProperties": False if strict else True,
            }

            # full JSON schema for the FunctionTool
            tool_schema: dict[str, Any] = {
                "type": "object",
                "properties": {
                    "parameters": parameters_obj_schema,
                },
                "required": ["parameters"],
                "additionalProperties": False if strict else True,
            }
            if req_body_schema:
                req_body_schema = req_body_schema.copy()
                if strict:
                    req_body_schema.setdefault("additionalProperties", False)
                tool_schema["properties"]["requestBody"] = req_body_schema
                tool_schema["required"].append("requestBody")

            # Callback factory  (captures current verb & path)

            async def _invoke(
                ctx: RunContextWrapper[Any],
                input_json: str,
                *,
                verb_: str = verb,
                path_: str = path,
            ):
                """Actual HTTP call executed by the agent."""
                payload = json.loads(input_json)

                # split out parts for old-style structure
                param_container: dict[str, Any] = payload.get("parameters", {})
                body_payload = payload.get("requestBody")

                url = f"{openapi['servers'][0]['url']}{path_}"
                for key, val in param_container.items():
                    token = f"{{{key}}}"
                    if token in url:
                        url = url.replace(token, str(val))
                        # null-out so it doesn't go into query string
                        param_container[key] = None
                url = url.rstrip("/")

                query_params = {k: v for k, v in param_container.items() if v is not None}
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

            if strict:
                tool_schema = ensure_strict_json_schema(tool_schema)

            tool = FunctionTool(
                name=function_name,
                description=description,
                params_json_schema=tool_schema,
                on_invoke_tool=_invoke,
                strict_json_schema=strict,
            )
            tools.append(tool)

    return tools


def validate_openapi_spec(spec: str):
    spec = json.loads(spec)

    # Validate that 'paths' is present in the spec
    if "paths" not in spec:
        raise ValueError("The spec must contain 'paths'.")

    for path, path_item in spec["paths"].items():
        # Check that each path item is a dictionary
        if not isinstance(path_item, dict):
            raise ValueError(f"Path item for '{path}' must be a dictionary.")

        for operation in path_item.values():
            # Basic validation for each operation
            if "operationId" not in operation:
                raise ValueError("Each operation must contain an 'operationId'.")
            if "description" not in operation:
                raise ValueError("Each operation must contain a 'description'.")

    return spec

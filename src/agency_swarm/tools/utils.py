from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional, Union

import httpx
import jsonref
from agents import FunctionTool
from agents.run_context import RunContextWrapper
from agents.strict_schema import ensure_strict_json_schema
from datamodel_code_generator import DataModelType, PythonVersion
from datamodel_code_generator.model import get_data_model_types
from datamodel_code_generator.parser.jsonschema import JsonSchemaParser

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
        strict (bool, optional): If True, sets 'additionalProperties' to False in every generated schema.
            Defaults to False.
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
    spec_dict = json.loads(spec)

    # Validate that 'paths' is present in the spec
    if "paths" not in spec_dict:
        raise ValueError("The spec must contain 'paths'.")

    paths = spec_dict["paths"]
    if not isinstance(paths, dict):
        raise ValueError("The 'paths' field must be a dictionary.")

    for path, path_item in paths.items():
        # Check that each path item is a dictionary
        if not isinstance(path_item, dict):
            raise ValueError(f"Path item for '{path}' must be a dictionary.")

        for operation in path_item.values():
            # Basic validation for each operation
            if "operationId" not in operation:
                raise ValueError("Each operation must contain an 'operationId'.")
            if "description" not in operation:
                raise ValueError("Each operation must contain a 'description'.")

    return spec_dict


def generate_model_from_schema(schema: dict, class_name: str, strict: bool) -> type:
    data_model_types = get_data_model_types(
        DataModelType.PydanticV2BaseModel,
        target_python_version=PythonVersion.PY_310,
    )
    parser = JsonSchemaParser(
        json.dumps(schema),
        data_model_type=data_model_types.data_model,
        data_model_root_type=data_model_types.root_model,
        data_model_field_type=data_model_types.field_model,
        data_type_manager_type=data_model_types.data_type_manager,
        dump_resolve_reference_action=data_model_types.dump_resolve_reference_action,
        use_schema_description=True,
        validation=False,
        class_name=class_name,
        strip_default_none=strict,
    )
    result = parser.parse()
    imports_str = "from typing import List, Dict, Any, Optional, Union, Set, Tuple, Literal\nfrom enum import Enum\n"
    if isinstance(result, str):
        result = imports_str + result
    else:
        result = imports_str + str(result)
    result = result.replace("from __future__ import annotations\n", "")
    result += f"\n\n{class_name}.model_rebuild(force=True)"
    exec_globals = {
        "List": list,
        "Dict": dict,
        "Type": type,
        "Union": Union,
        "Optional": Optional,
        "datetime": datetime,
        "date": date,
        "Set": set,
        "Tuple": tuple,
        "Any": Any,
        "Callable": Callable,
        "Decimal": Decimal,
        "Literal": Literal,
        "Enum": Enum,
    }
    exec(result, exec_globals)
    model = exec_globals.get(class_name)
    if not model:
        raise ValueError(f"Could not extract model from schema {class_name}")
    if hasattr(model, "model_rebuild"):
        try:
            model.model_rebuild(force=True)
        except Exception as e:
            print(f"Warning: Could not rebuild model {class_name} after exec: {e}")
    return model  # type: ignore[return-value]

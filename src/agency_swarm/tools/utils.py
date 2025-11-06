import base64
import json
import logging
import mimetypes
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Optional, Union

import httpx
import jsonref
from agents import FunctionTool, ToolOutputFileContent, ToolOutputImage
from agents.run_context import RunContextWrapper
from agents.strict_schema import ensure_strict_json_schema
from datamodel_code_generator import DataModelType, PythonVersion
from datamodel_code_generator.model import get_data_model_types
from datamodel_code_generator.parser.jsonschema import JsonSchemaParser

logger = logging.getLogger(__name__)

PDF_MIME_TYPE = "application/pdf"


def _build_data_url(file_path: Path, mime_type: str) -> str:
    encoded_file = base64.b64encode(file_path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded_file}"


def _resolve_mime_type(file_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(file_path.name)
    if not mime_type:
        raise ValueError(f"Unable to determine MIME type for file: {file_path}")
    return mime_type


def tool_output_image_from_path(
    path: str | Path,
    *,
    detail: Literal["auto", "high", "low"] = "auto",
) -> ToolOutputImage:
    """
    Build a ``ToolOutputImage`` from a local image file by returning a data URL.

    Args:
        path: Path to the image file on disk.
        detail: Optional detail hint to forward to the vision model.

    Raises:
        ValueError: If the file type cannot be resolved from the path.
    """

    file_path = Path(path)
    mime_type = _resolve_mime_type(file_path)
    return ToolOutputImage(image_url=_build_data_url(file_path, mime_type), detail=detail)


def tool_output_image_from_file_id(
    file_id: str,
    *,
    detail: Literal["auto", "high", "low"] = "auto",
) -> ToolOutputImage:
    """
    Build a ``ToolOutputImage`` from an OpenAI file ID.

    Args:
        file_id: openai file id of the image file.
        detail: Optional detail hint to forward to the vision model.
    """

    return ToolOutputImage(file_id=file_id, detail=detail)


def tool_output_file_from_path(path: str | Path, *, filename: str | None = None) -> ToolOutputFileContent:
    """
    Build a ``ToolOutputFileContent`` from a local file by embedding base64 data.

    Args:
        path: Path to the file on disk.
        filename: Optional filename hint for the client.

    Raises:
        ValueError: If the file is not a PDF.
    """

    file_path = Path(path)
    if filename and not filename.lower().endswith(".pdf"):
        raise ValueError(f"Filename must end with .pdf, got: {filename}")
    mime_type = _resolve_mime_type(file_path)
    if mime_type != PDF_MIME_TYPE:
        raise ValueError("Only PDF files are supported.")
    return ToolOutputFileContent(
        file_data=_build_data_url(file_path, PDF_MIME_TYPE), filename=filename or file_path.name
    )


def tool_output_file_from_url(url: str) -> ToolOutputFileContent:
    """
    Build a ``ToolOutputFileContent`` that references an externally hosted file.

    Args:
        url: Publicly reachable URL for the file.
    """

    return ToolOutputFileContent(file_url=url)


def tool_output_file_from_file_id(file_id: str) -> ToolOutputFileContent:
    """
    Build a ``ToolOutputFileContent`` that references an openai file id.

    Args:
        file_id: openai file id of the pdf file.
    """

    return ToolOutputFileContent(file_id=file_id)


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

    base_url = openapi["servers"][0]["url"]

    for path, verbs in openapi["paths"].items():
        for verb, verb_spec_ref in verbs.items():
            verb_spec = jsonref.replace_refs(verb_spec_ref)

            # Build OpenAI-compatible JSON schema

            function_name = verb_spec.get("operationId")
            description = verb_spec.get("description") or verb_spec.get("summary", "")

            req_body_schema = (
                verb_spec.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            )

            parameters_obj_schema = build_parameter_object_schema(
                verb_spec.get("parameters", []),
                strict,
            )

            tool_schema = build_tool_schema(parameters_obj_schema, req_body_schema, strict=strict)

            # Callback factory  (captures current verb & path)

            async def _invoke(
                ctx: RunContextWrapper[Any],
                input_json: str,
                *,
                verb_: str = verb,
                path_: str = path,
                base_url_: str = base_url,
            ):
                """Actual HTTP call executed by the agent."""
                payload = json.loads(input_json)

                # split out parts for old-style structure
                raw_parameters: dict[str, Any] = payload.get("parameters", {})
                body_payload = payload.get("requestBody")

                url, remaining_params = resolve_url(base_url_, path_, raw_parameters)

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


def collect_parameter_schemas(parameters: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    """Extract parameter schemas and required flags from an OpenAPI operation."""
    properties: dict[str, Any] = {}
    required: list[str] = []

    for parameter in parameters:
        if "schema" not in parameter and "type" in parameter:
            parameter["schema"] = {"type": parameter["type"]}

        schema = parameter.get("schema")
        if not schema:
            raise ValueError(f"Parameter '{parameter['name']}' must define a schema")

        property_schema = properties.setdefault(parameter["name"], schema.copy())

        for attribute in ("description", "example", "examples"):
            if attribute in parameter:
                property_schema[attribute] = parameter[attribute]

        if parameter.get("required"):
            required.append(parameter["name"])

    return properties, required


def build_parameter_object_schema(parameters: list[dict[str, Any]], strict: bool) -> dict[str, Any]:
    properties, required = collect_parameter_schemas(parameters)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False if strict else True,
    }


def build_tool_schema(
    parameter_schema: dict[str, Any],
    request_body_schema: dict[str, Any] | None,
    *,
    strict: bool,
    include_strict_flag: bool = False,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {"parameters": parameter_schema},
        "required": ["parameters"],
        "additionalProperties": False if strict else True,
    }

    if include_strict_flag and strict:
        schema["strict"] = True

    if request_body_schema:
        body_schema = request_body_schema.copy()
        if strict:
            body_schema.setdefault("additionalProperties", False)
        schema["properties"]["requestBody"] = body_schema
        schema["required"].append("requestBody")

    return ensure_strict_json_schema(schema) if strict else schema


def resolve_url(base_url: str, path: str, parameters: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Replace templated path parameters and return remaining query parameters."""
    url = f"{base_url}{path}"
    remaining_params: dict[str, Any] = {}

    for key, value in parameters.items():
        token = f"{{{key}}}"
        if token in url:
            url = url.replace(token, str(value))
            continue
        remaining_params[key] = value

    return url.rstrip("/"), remaining_params

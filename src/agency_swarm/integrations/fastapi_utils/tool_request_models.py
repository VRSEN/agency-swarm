from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, create_model

from agency_swarm.tools.tool_factory_utils.schema_inspector import supports_request_model


def build_request_model(
    parameters: dict[str, Any],
    tool_name: str,
    *,
    strict: bool = False,
) -> type[BaseModel] | None:
    if not parameters or not supports_request_model(parameters):
        return None

    defs = parameters.get("$defs", {})
    def_models: dict[str, type[BaseModel]] = {}

    field_definitions: dict[str, Any] = {}
    properties = parameters.get("properties", {})
    required = parameters.get("required", [])

    for field_name, field_info in properties.items():
        field_type = _resolve_field_type(
            field_info,
            inline_name=field_name.title(),
            tool_name=tool_name,
            defs=defs,
            def_models=def_models,
            strict=strict,
        )
        if field_type is None:
            return None

        field_desc = field_info.get("description", "")
        is_required = field_name in required and "default" not in field_info

        if is_required:
            field_definitions[field_name] = (field_type, Field(..., description=field_desc))
        else:
            default_val = field_info.get("default", None)
            field_definitions[field_name] = (field_type | None, Field(default_val, description=field_desc))

    if not field_definitions:
        return None

    return _create_model_with_config(f"{tool_name}Request", field_definitions, parameters, strict)


def _resolve_field_type(
    field_info: dict[str, Any],
    *,
    inline_name: str,
    tool_name: str,
    defs: dict[str, Any],
    def_models: dict[str, type[BaseModel]],
    strict: bool,
) -> Any | None:
    if "$ref" in field_info:
        ref_path = field_info["$ref"]
        if not ref_path.startswith("#/$defs/"):
            return None
        def_name = ref_path.replace("#/$defs/", "")
        return _ensure_def_model(def_name, defs, def_models, strict, tool_name)

    field_type = field_info.get("type")
    if field_type == "array":
        items_info = field_info.get("items", {})
        if not items_info:
            return list
        item_type = _resolve_field_type(
            items_info,
            inline_name=f"{inline_name}Item",
            tool_name=tool_name,
            defs=defs,
            def_models=def_models,
            strict=strict,
        )
        if item_type is None:
            return None
        list_type = list.__class_getitem__((item_type,))
        return cast(type, list_type)

    if field_type == "object":
        properties = field_info.get("properties", {})
        if not properties:
            return dict

        nested_required = field_info.get("required", [])
        nested_fields: dict[str, Any] = {}
        for prop_name, prop_info in properties.items():
            prop_type = _resolve_field_type(
                prop_info,
                inline_name=f"{inline_name}{prop_name.title()}",
                tool_name=tool_name,
                defs=defs,
                def_models=def_models,
                strict=strict,
            )
            if prop_type is None:
                return None
            prop_desc = prop_info.get("description", "")
            is_required = prop_name in nested_required and "default" not in prop_info
            if is_required:
                nested_fields[prop_name] = (prop_type, Field(..., description=prop_desc))
            else:
                default_val = prop_info.get("default", None)
                nested_fields[prop_name] = (prop_type | None, Field(default_val, description=prop_desc))

        if not nested_fields:
            return None

        inline_model_name = f"{tool_name}{inline_name}"
        return _create_model_with_config(inline_model_name, nested_fields, field_info, strict)

    if field_type in {"string", "number", "integer", "boolean"}:
        type_mapping = {
            "string": str,
            "number": float,
            "integer": int,
            "boolean": bool,
        }
        return type_mapping[field_type]

    if field_type == "null":  # pragma: no cover - unsupported escape hatch
        return type(None)

    if field_type is None:
        return str

    return str


def _ensure_def_model(
    def_name: str,
    defs: dict[str, Any],
    def_models: dict[str, type[BaseModel]],
    strict: bool,
    tool_name: str,
) -> type[BaseModel] | None:
    if def_name in def_models:
        return def_models[def_name]

    def_schema = defs.get(def_name)
    if def_schema is None:
        return None

    nested_fields: dict[str, Any] = {}
    nested_required = def_schema.get("required", [])

    for prop_name, prop_info in def_schema.get("properties", {}).items():
        prop_type = _resolve_field_type(
            prop_info,
            inline_name=f"{def_name}{prop_name.title()}",
            tool_name=tool_name,
            defs=defs,
            def_models=def_models,
            strict=strict,
        )
        if prop_type is None:
            return None

        prop_desc = prop_info.get("description", "")
        is_required = prop_name in nested_required and "default" not in prop_info

        if is_required:
            nested_fields[prop_name] = (prop_type, Field(..., description=prop_desc))
        else:
            default_val = prop_info.get("default", None)
            nested_fields[prop_name] = (prop_type | None, Field(default_val, description=prop_desc))

    if not nested_fields:
        return None

    def_models[def_name] = _create_model_with_config(def_name, nested_fields, def_schema, strict)
    return def_models[def_name]


def _create_model_with_config(
    model_name: str,
    field_definitions: dict[str, Any],
    schema_section: dict[str, Any],
    strict: bool,
) -> type[BaseModel]:
    config_kwargs: dict[str, Any] = {}
    if _should_forbid_extra(schema_section, strict):
        config_kwargs["__config__"] = ConfigDict(extra="forbid")
    return create_model(model_name, **config_kwargs, **field_definitions)


def _should_forbid_extra(schema_section: dict[str, Any], strict: bool) -> bool:
    additional_properties = schema_section.get("additionalProperties")
    if isinstance(additional_properties, bool):
        return not additional_properties
    return strict

from __future__ import annotations

from typing import Any


def supports_request_model(parameters_schema: dict[str, Any]) -> bool:
    properties = parameters_schema.get("properties") or {}
    if not properties:
        return False
    defs = parameters_schema.get("$defs", {})
    return not _schema_has_polymorphism(parameters_schema, defs, set())


def _schema_has_polymorphism(
    schema_section: dict[str, Any],
    defs: dict[str, Any],
    visited_defs: set[str],
) -> bool:
    for keyword in ("oneOf", "anyOf", "allOf"):
        if keyword in schema_section:
            return True

    ref = schema_section.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        def_name = ref.replace("#/$defs/", "")
        if def_name in visited_defs:
            return False
        visited_defs.add(def_name)
        def_schema = defs.get(def_name)
        if isinstance(def_schema, dict) and _schema_has_polymorphism(def_schema, defs, visited_defs):
            return True
        visited_defs.remove(def_name)

    if "properties" in schema_section and isinstance(schema_section["properties"], dict):
        for value in schema_section["properties"].values():
            if isinstance(value, dict) and _schema_has_polymorphism(value, defs, visited_defs):
                return True

    if "items" in schema_section and isinstance(schema_section["items"], dict):
        if _schema_has_polymorphism(schema_section["items"], defs, visited_defs):
            return True

    return False

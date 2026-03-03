from __future__ import annotations

import pytest
from pydantic import ValidationError

from agency_swarm.integrations.fastapi_utils.tool_request_models import build_request_model


def test_build_request_model_returns_none_for_empty_and_polymorphic_schema() -> None:
    assert build_request_model({}, "Empty") is None
    assert build_request_model({"type": "object", "properties": {}}, "NoProps") is None

    polymorphic = {
        "type": "object",
        "properties": {
            "choice": {
                "oneOf": [
                    {"type": "string"},
                    {"type": "integer"},
                ]
            }
        },
    }
    assert build_request_model(polymorphic, "Poly") is None


def test_build_request_model_supports_defs_and_strict_forbid_extra() -> None:
    schema = {
        "type": "object",
        "properties": {
            "config": {"$ref": "#/$defs/Config"},
        },
        "required": ["config"],
        "$defs": {
            "Config": {
                "type": "object",
                "properties": {
                    "enabled": {"type": "boolean"},
                },
                "required": ["enabled"],
            }
        },
    }

    request_model = build_request_model(schema, "ConfigTool", strict=True)
    assert request_model is not None

    parsed = request_model.model_validate({"config": {"enabled": True}})
    assert parsed.config.enabled is True

    with pytest.raises(ValidationError):
        request_model.model_validate({"config": {"enabled": True, "extra": 1}})


def test_build_request_model_handles_array_object_null_and_untyped_fields() -> None:
    schema = {
        "type": "object",
        "properties": {
            "arr": {"type": "array"},
            "obj": {"type": "object"},
            "maybe_null": {"type": "null"},
            "mystery": {"type": "custom"},
            "untyped": {},
        },
        "required": ["arr", "obj", "maybe_null", "mystery", "untyped"],
    }

    request_model = build_request_model(schema, "Mixed")
    assert request_model is not None

    parsed = request_model.model_validate(
        {
            "arr": [1, "two"],
            "obj": {"anything": "goes"},
            "maybe_null": None,
            "mystery": "value",
            "untyped": "text",
        }
    )
    assert parsed.arr == [1, "two"]
    assert parsed.obj == {"anything": "goes"}
    assert parsed.maybe_null is None
    assert parsed.mystery == "value"
    assert parsed.untyped == "text"


def test_build_request_model_rejects_invalid_refs() -> None:
    unsupported_ref = {
        "type": "object",
        "properties": {
            "cfg": {"$ref": "#/components/schemas/Config"},
        },
    }
    assert build_request_model(unsupported_ref, "BadRef") is None

    missing_def = {
        "type": "object",
        "properties": {
            "cfg": {"$ref": "#/$defs/Config"},
        },
        "$defs": {},
    }
    assert build_request_model(missing_def, "MissingDef") is None


def test_build_request_model_respects_additional_properties_over_strict_flag() -> None:
    allow_extra_schema = {
        "type": "object",
        "additionalProperties": True,
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    allow_model = build_request_model(allow_extra_schema, "AllowExtra", strict=True)
    assert allow_model is not None
    allow_model.model_validate({"name": "ok", "extra": "ignored"})

    forbid_extra_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    forbid_model = build_request_model(forbid_extra_schema, "ForbidExtra", strict=False)
    assert forbid_model is not None

    with pytest.raises(ValidationError):
        forbid_model.model_validate({"name": "ok", "extra": "blocked"})

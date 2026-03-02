"""Unit tests for BaseTool functionality."""

import pytest
from agents import RunContextWrapper
from pydantic import BaseModel

from agency_swarm.context import MasterContext
from agency_swarm.tools.base_tool import BaseTool, classproperty


class SampleTool(BaseTool):
    name: str = "sample"

    def run(self) -> str:
        return "ok"


def test_classproperty_descriptor_supports_plain_and_basetool_access() -> None:
    """classproperty should resolve for plain classes and BaseTool subclasses."""

    class Demo:
        _value = "value"

        @classproperty
        def prop(cls):
            return cls._value

    assert Demo.prop == "value"
    assert Demo().prop == "value"

    class ToolWithClassProp(BaseTool):
        name: str = "name"

        @classproperty
        def computed(cls):
            return "computed-value"

        def run(self) -> str:
            return self.name

    tool = ToolWithClassProp()
    assert tool.name == "name"
    assert tool.computed == "computed-value"


def test_base_tool_requires_run_implementation() -> None:
    """BaseTool and incomplete subclasses should remain abstract."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class BaseTool"):
        BaseTool()

    with pytest.raises(TypeError, match="Can't instantiate abstract class.*run"):

        class IncompleteTool(BaseTool):
            pass

        IncompleteTool()


def test_base_tool_initialization_and_tool_config_defaults() -> None:
    """Concrete tools should initialize context wrapper and preserve ToolConfig defaults/overrides."""
    tool = SampleTool()
    assert tool.name == "sample"
    assert isinstance(tool._context, RunContextWrapper)
    assert isinstance(tool._context.context, MasterContext)
    assert tool.ToolConfig.strict is False
    assert tool.ToolConfig.one_call_at_a_time is False

    class StrictSequentialTool(BaseTool):
        class ToolConfig:
            strict = True
            one_call_at_a_time = True
            custom_flag = "kept"

        def run(self) -> str:
            return "ok"

    tool = StrictSequentialTool()
    assert tool.ToolConfig.strict is True
    assert tool.ToolConfig.one_call_at_a_time is True
    assert tool.ToolConfig.custom_flag == "kept"


def test_openai_schema_descriptions_required_fields_and_fallback() -> None:
    """OpenAI schema should include docstring details and apply fallback descriptions when absent."""

    class DocumentedTool(BaseTool):
        """A tool for schema checks.

        Args:
            name: Name field description
            count: Count field description
        """

        name: str
        count: int = 5

        def run(self) -> str:
            return f"{self.name}:{self.count}"

    schema = DocumentedTool.openai_schema
    params = schema["parameters"]

    assert schema["name"] == "DocumentedTool"
    assert "A tool for schema checks." in schema["description"]
    assert params["properties"]["name"]["description"] == "Name field description"
    assert params["properties"]["count"]["description"] == "Count field description"
    assert "name" in params["required"]
    assert "count" not in params["required"]

    class UndocumentedTool(BaseTool):
        def run(self) -> str:
            return "ok"

    schema = UndocumentedTool.openai_schema
    assert schema["description"] == "`UndocumentedTool` tool"


def test_openai_schema_strict_mode_applies_additional_properties_to_main_and_defs() -> None:
    """Strict mode should set additionalProperties=False on root and nested definitions."""

    class NestedModel(BaseModel):
        nested_field: str
        optional_field: int | None = None

    class StrictTool(BaseTool):
        class ToolConfig:
            strict = True

        name: str
        payload: list[NestedModel]

        def run(self) -> str:
            return "ok"

    schema = StrictTool.openai_schema
    assert schema["strict"] is True
    assert schema["parameters"]["additionalProperties"] is False

    defs = schema["parameters"].get("$defs", {})
    for definition in defs.values():
        assert definition["additionalProperties"] is False


def test_base_tool_context_property_and_removed_shared_state() -> None:
    """context property should proxy MasterContext and _shared_state should be unavailable."""
    tool = SampleTool()

    assert isinstance(tool.context, MasterContext)

    tool._context = None
    assert tool.context is None

    with pytest.raises(AttributeError, match=r"_shared_state"):
        _ = tool._shared_state

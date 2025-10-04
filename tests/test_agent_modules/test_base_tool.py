"""
Unit tests for BaseTool functionality.

Tests the core BaseTool class including schema generation, context management,
and configuration handling.
"""

import warnings

import pytest
from agents import RunContextWrapper
from pydantic import BaseModel

from agency_swarm.context import MasterContext
from agency_swarm.tools.base_tool import BaseTool, classproperty


class TestClassProperty:
    """Test the classproperty descriptor."""

    def test_classproperty_descriptor(self):
        """Test that classproperty works as a class-level property."""

        class TestClass:
            _value = "test_value"

            @classproperty
            def class_prop(cls):
                return cls._value

        # Test access through class
        assert TestClass.class_prop == "test_value"

        # Test access through instance
        instance = TestClass()
        assert instance.class_prop == "test_value"

        # Test that classproperty returns the owner class to the function
        @classproperty
        def get_owner(cls):
            return cls

        TestClass.get_owner_prop = get_owner
        assert TestClass.get_owner_prop is TestClass


class TestBaseTool:
    """Test BaseTool functionality."""

    def test_abstract_base_tool_cannot_be_instantiated(self):
        """Test that BaseTool cannot be instantiated directly due to abstract method."""

        with pytest.raises(TypeError, match="Can't instantiate abstract class BaseTool"):
            BaseTool()

    def test_concrete_tool_initialization(self):
        """Test initialization of a concrete BaseTool subclass."""

        class ConcreteTool(BaseTool):
            name: str = "test"

            def run(self):
                return "executed"

        tool = ConcreteTool()
        assert tool.name == "test"
        assert hasattr(tool, "_caller_agent")
        assert hasattr(tool, "_event_handler")
        assert hasattr(tool, "_context")

    def test_tool_config_defaults_initialization(self):
        """Test that ToolConfig defaults are properly set during initialization."""

        class ToolWithoutStrictConfig(BaseTool):
            class ToolConfig:
                pass

            def run(self):
                return "test"

        tool = ToolWithoutStrictConfig()
        # Test that strict default was added
        assert hasattr(tool.ToolConfig, "strict")
        assert tool.ToolConfig.strict is False

    def test_tool_config_preserves_existing_values(self):
        """Test that existing ToolConfig values are not overridden."""

        class ToolWithExistingConfig(BaseTool):
            class ToolConfig:
                strict = True
                custom_setting = "preserved"

            def run(self):
                return "test"

        tool = ToolWithExistingConfig()
        # Test that existing values are preserved
        assert tool.ToolConfig.strict is True
        assert tool.ToolConfig.custom_setting == "preserved"

    def test_context_initialization(self):
        """Test that context is properly initialized when not provided."""

        class TestTool(BaseTool):
            def run(self):
                return "test"

        tool = TestTool()
        assert tool._context is not None
        assert isinstance(tool._context, RunContextWrapper)
        assert isinstance(tool._context.context, MasterContext)

    def test_context_initialization_behavior(self):
        """Test context initialization behavior."""

        class TestTool(BaseTool):
            def run(self):
                return "test"

        # Test that context is always initialized
        tool = TestTool()

        # Re-initialize
        tool.__init__()

        # Context will be re-created (this is the actual behavior)
        assert tool._context is not None
        assert isinstance(tool._context, RunContextWrapper)

    def test_openai_schema_generation(self):
        """Test OpenAI schema generation from model and docstring."""

        class DocumentedTool(BaseTool):
            """A tool for testing schema generation.

            Args:
                name: The name parameter
                count: Number of items to process
            """

            name: str
            count: int = 5

            def run(self):
                return f"Processed {self.count} items named {self.name}"

        schema = DocumentedTool.openai_schema

        assert schema["name"] == "DocumentedTool"
        # The actual implementation includes the full docstring including Args section
        assert "A tool for testing schema generation." in schema["description"]
        assert "Args:" in schema["description"]
        assert "parameters" in schema

        # Check parameters structure
        params = schema["parameters"]
        assert "properties" in params
        assert "name" in params["properties"]
        assert "count" in params["properties"]

        # Check that docstring descriptions were added
        assert params["properties"]["name"]["description"] == "The name parameter"
        assert params["properties"]["count"]["description"] == "Number of items to process"

        # Check required fields (should include 'name' but not 'count' which has default)
        assert "name" in params["required"]
        assert "count" not in params["required"]

    def test_openai_schema_without_docstring(self):
        """Test schema generation for tool without docstring."""

        class UndocumentedTool(BaseTool):
            name: str

            def run(self):
                return "test"

        schema = UndocumentedTool.openai_schema

        assert schema["name"] == "UndocumentedTool"
        # Should generate default description
        expected_desc = "`UndocumentedTool` tool"
        assert schema["description"] == expected_desc

    def test_openai_schema_with_strict_mode(self):
        """Test schema generation with strict mode enabled."""

        class StrictTool(BaseTool):
            """A strict tool."""

            class ToolConfig:
                strict = True

            name: str

            def run(self):
                return "test"

        schema = StrictTool.openai_schema

        assert schema["strict"] is True
        assert schema["parameters"]["additionalProperties"] is False

    def test_openai_schema_with_defs_strict_mode(self):
        """Test schema generation with $defs and strict mode using real data."""

        class NestedData(BaseModel):
            nested_field: str
            optional_field: int | None = None

        class ComplexTool(BaseTool):
            """Tool with complex nested types that should generate $defs."""

            class ToolConfig:
                strict = True

            name: str
            data_list: list[NestedData]

            def run(self):
                return f"Processed {len(self.data_list)} items"

        schema = ComplexTool.openai_schema

        # Check that schema has the expected structure
        assert schema["strict"] is True
        assert schema["parameters"]["additionalProperties"] is False

        # Check if $defs were actually generated by Pydantic
        if "$defs" in schema["parameters"]:
            # If $defs exist, verify they all have additionalProperties set to False
            for def_name, def_schema in schema["parameters"]["$defs"].items():
                assert def_schema["additionalProperties"] is False, (
                    f"Definition '{def_name}' missing additionalProperties: False"
                )

        # Verify the tool works with actual parameters
        assert "name" in schema["parameters"]["properties"]
        assert "data_list" in schema["parameters"]["properties"]

    def test_openai_schema_without_docstring_or_schema_description(self):
        """Test that tools without docstring get default description with class name."""

        class PlainTool(BaseTool):
            def run(self):
                return "test"

        schema = PlainTool.openai_schema

        # Should generate default description with class name
        expected_desc = "`PlainTool` tool"
        assert schema["description"] == expected_desc

    def test_context_property_access(self):
        """Test the context property provides access to MasterContext."""

        class TestTool(BaseTool):
            def run(self):
                return "test"

        tool = TestTool()
        context = tool.context

        assert context is not None
        assert isinstance(context, MasterContext)
        assert context is tool._context.context

    def test_context_property_when_context_is_none(self):
        """Test context property returns None when _context is None."""

        class TestTool(BaseTool):
            def run(self):
                return "test"

        tool = TestTool()
        tool._context = None

        assert tool.context is None

    def test_shared_state_property_deprecation_warning(self):
        """Test that _shared_state property raises deprecation warning."""

        class TestTool(BaseTool):
            def run(self):
                return "test"

        tool = TestTool()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            context = tool._shared_state

            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "_shared_state is deprecated" in str(w[0].message)
            assert "Use 'self.context' instead" in str(w[0].message)

            # Should return same as context property
            assert context is tool.context

    def test_model_config_ignores_classproperty(self):
        """Test that model_config properly ignores classproperty types."""

        class TestTool(BaseTool):
            name: str = "test"

            @classproperty
            def my_class_prop(cls):
                return "class_value"

            def run(self):
                return "test"

        tool = TestTool()

        # Should be able to create tool without issues from classproperty
        assert tool.name == "test"
        assert tool.my_class_prop == "class_value"

    def test_tool_config_one_call_at_a_time_default(self):
        """Test that one_call_at_a_time has proper default value."""

        class TestTool(BaseTool):
            def run(self):
                return "test"

        tool = TestTool()
        assert hasattr(tool.ToolConfig, "one_call_at_a_time")
        assert tool.ToolConfig.one_call_at_a_time is False

    def test_tool_config_custom_one_call_at_a_time(self):
        """Test that custom one_call_at_a_time value is preserved."""

        class ConcurrentTool(BaseTool):
            class ToolConfig:
                one_call_at_a_time = True

            def run(self):
                return "test"

        tool = ConcurrentTool()
        assert tool.ToolConfig.one_call_at_a_time is True

    def test_run_method_is_abstract(self):
        """Test that the run method is properly abstract."""

        # This should work - defining run method
        class CompleteTool(BaseTool):
            def run(self):
                return "complete"

        tool = CompleteTool()
        assert tool.run() == "complete"

        # This should fail - not implementing run method
        with pytest.raises(TypeError, match="Can't instantiate abstract class.*run"):

            class IncompleteTool(BaseTool):
                pass

            IncompleteTool()

    def test_openai_schema_uses_docstring_description(self):
        """Test that docstring description is used when available."""

        class ToolWithDocstring(BaseTool):
            """This is a tool with a clear docstring description."""

            name: str

            def run(self):
                return f"Processing {self.name}"

        schema = ToolWithDocstring.openai_schema

        # Should use the docstring description
        assert "This is a tool with a clear docstring description." in schema["description"]

    def test_parameter_description_from_docstring(self):
        """Test that parameter descriptions are extracted from docstring."""

        class TestTool(BaseTool):
            """Tool with documented parameters.

            Args:
                name: The name of the item to process
                count: Number of items to handle
            """

            name: str
            count: int = 5

            def run(self):
                return f"Processing {self.name} with count {self.count}"

        schema = TestTool.openai_schema

        # Should extract descriptions from docstring
        params = schema["parameters"]["properties"]
        assert params["name"]["description"] == "The name of the item to process"
        assert params["count"]["description"] == "Number of items to handle"

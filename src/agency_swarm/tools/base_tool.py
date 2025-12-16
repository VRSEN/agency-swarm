"""
This module provides the BaseTool class for creating Pydantic-based tools in Agency Swarm.

BaseTool is an alternative to @function_tool decorators, offering explicit field definitions,
model validators, and Pydantic's validation features. Both BaseTool and @function_tool
are fully supported approaches for tool creation.
"""

import copy
import warnings
from abc import ABC, abstractmethod
from typing import Any

from agents import RunContextWrapper
from docstring_parser import parse
from pydantic import BaseModel

from ..context import MasterContext


class classproperty:
    def __init__(self, fget):
        self.fget = fget

    def __get__(self, instance, owner):
        return self.fget(owner)


class BaseToolMeta(type(BaseModel)):  # type: ignore[misc]
    """Metaclass for BaseTool that provides a nice __repr__ for the class itself."""

    def __repr__(cls):  # type: ignore[override]
        """Return a detailed representation of the BaseTool class."""
        try:
            # Get the full schema with all nested definitions
            schema = cls.model_json_schema()

            # Resolve all $ref references inline for better readability
            if "$defs" in schema:
                defs = schema.get("$defs", {})

                def resolve_refs(obj):
                    """Recursively resolve all $ref references in the schema."""
                    if isinstance(obj, dict):
                        if "$ref" in obj:
                            ref_path = obj["$ref"]
                            if ref_path.startswith("#/$defs/"):
                                def_name = ref_path.split("/")[-1]
                                if def_name in defs:
                                    # Return a copy of the definition to avoid circular references
                                    resolved = copy.deepcopy(defs[def_name])
                                    # Recursively resolve any nested refs
                                    return resolve_refs(resolved)
                            return obj
                        else:
                            # Recursively process all values in the dict
                            return {k: resolve_refs(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [resolve_refs(item) for item in obj]
                    return obj

                # Resolve all refs in the schema
                schema = resolve_refs(schema)
                # Remove $defs since everything is now inlined
                schema.pop("$defs", None)

            return f"{cls.__name__}(description={cls.__doc__!r}, params_json_schema={schema})"
        except Exception:
            # Fallback to default repr if schema generation fails
            return super().__repr__()


class BaseTool(BaseModel, ABC, metaclass=BaseToolMeta):
    model_config = {"ignored_types": (classproperty,)}

    _caller_agent: Any = None
    _event_handler: Any = None
    _context: Any = None  # Will hold RunContextWrapper when available

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Ensure all ToolConfig variables are initialized
        config_defaults = {
            "strict": False,
        }

        for key, value in config_defaults.items():
            if not hasattr(self.ToolConfig, key):
                setattr(self.ToolConfig, key, value)

        if self._context is None:
            self._context = RunContextWrapper(
                context=MasterContext(thread_manager=None, agents={}, user_context={}, current_agent_name=None)
            )

    def __repr__(self) -> str:
        """Return a detailed representation of the BaseTool instance."""
        schema = self.model_json_schema()
        return f"{self.__class__.__name__}(description={self.__class__.__doc__!r}, params_json_schema={schema})"

    class ToolConfig:
        strict: bool = False
        # When True, this tool runs with a one-call-at-a-time policy per agent; any concurrent
        # tool call for the same agent will immediately error until completion.
        one_call_at_a_time: bool = False

    @classproperty
    def openai_schema(cls) -> dict[str, Any]:
        """
        Return the schema in the format of OpenAI's schema as jsonschema

        Note:
            It's important to add a docstring to describe how to best use this class;
            it will be included in the description attribute and be part of the prompt.

        Returns:
            model_json_schema (dict): A dictionary in the format of OpenAI's schema as jsonschema
        """
        schema = cls.model_json_schema()
        docstring = parse(cls.__doc__ or "")
        parameters = {k: v for k, v in schema.items() if k not in ("title", "description")}
        for param in docstring.params:
            if (name := param.arg_name) in parameters["properties"] and (description := param.description):
                if "description" not in parameters["properties"][name]:
                    parameters["properties"][name]["description"] = description

        parameters["required"] = sorted(k for k, v in parameters["properties"].items() if "default" not in v)

        if "description" not in schema:
            if docstring.short_description:
                schema["description"] = docstring.short_description
            else:
                class_name = cls.__name__ if hasattr(cls, "__name__") else "Tool"
                schema["description"] = f"`{class_name}` tool"

        schema = {
            "name": schema["title"],
            "description": schema["description"],
            "parameters": parameters,
        }

        strict = getattr(cls.ToolConfig, "strict", False)
        if strict:
            schema["strict"] = True
            schema["parameters"]["additionalProperties"] = False
            # iterate through defs and set additionalProperties to false
            if "$defs" in schema["parameters"]:
                for def_ in schema["parameters"]["$defs"].values():
                    def_["additionalProperties"] = False

        return schema

    @property
    def context(self) -> MasterContext | None:
        """Get the MasterContext if available, providing clean access to shared state."""
        if self._context is not None:
            return self._context.context
        return None

    @property
    def _shared_state(self) -> MasterContext | None:
        """
        Backwards compatibility property that provides direct access to the context.

        Usage:
        - self._shared_state.set("key", "value")  # Set a value
        - value = self._shared_state.get("key", "default")  # Get a value
        """
        warnings.warn(
            "_shared_state is deprecated and will be removed in future versions. Use 'self.context' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.context

    @abstractmethod
    def run(self):
        pass

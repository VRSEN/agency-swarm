"""
This module is provided solely to ensure backwards compatibility with previous versions of the Agency Swarm framework.
It is deprecated and should not be used for new development.
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from docstring_parser import parse
from openai.types.beta.threads.runs.tool_call import ToolCall
from pydantic import BaseModel


class classproperty:
    def __init__(self, fget):
        self.fget = fget

    def __get__(self, instance, owner):
        return self.fget(owner)


class BaseTool(BaseModel, ABC):
    _caller_agent: Any = None
    _event_handler: Any = None
    _tool_call: ToolCall = None
    openai_schema: ClassVar[dict[str, Any]]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Ensure all ToolConfig variables are initialized
        config_defaults = {
            "strict": False,
        }

        for key, value in config_defaults.items():
            if not hasattr(self.ToolConfig, key):
                setattr(self.ToolConfig, key, value)

    class ToolConfig:
        strict: bool = False

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
                schema["description"] = (
                    f"Correctly extracted `{cls.__name__}` with all the required parameters with correct types"
                )

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

    @abstractmethod
    def run(self):
        pass

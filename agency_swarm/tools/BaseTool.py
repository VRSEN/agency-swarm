from abc import ABC, abstractmethod
from typing import Any, ClassVar

from docstring_parser import parse

from pydantic import BaseModel
from agency_swarm.util.shared_state import SharedState


class BaseTool(BaseModel, ABC):
    _shared_state: ClassVar[SharedState] = None
    _caller_agent: Any = None
    _event_handler: Any = None

    def __init__(self, **kwargs):
        if not self.__class__._shared_state:
            self.__class__._shared_state = SharedState()
        super().__init__(**kwargs)

    class ToolConfig:
        strict: bool = False
        one_call_at_a_time: bool = False

    @classmethod
    @property
    def openai_schema(cls):
        """
        Return the schema in the format of OpenAI's schema as jsonschema

        Note:
            Its important to add a docstring to describe how to best use this class, it will be included in the description attribute and be part of the prompt.

        Returns:
            model_json_schema (dict): A dictionary in the format of OpenAI's schema as jsonschema
        """
        schema = cls.model_json_schema()
        docstring = parse(cls.__doc__ or "")
        parameters = {
            k: v for k, v in schema.items() if k not in ("title", "description")
        }
        for param in docstring.params:
            if (name := param.arg_name) in parameters["properties"] and (
                description := param.description
            ):
                if "description" not in parameters["properties"][name]:
                    parameters["properties"][name]["description"] = description

        parameters["required"] = sorted(
            k for k, v in parameters["properties"].items() if "default" not in v
        )

        if "description" not in schema:
            if docstring.short_description:
                schema["description"] = docstring.short_description
            else:
                schema["description"] = (
                    f"Correctly extracted `{cls.__name__}` with all "
                    f"the required parameters with correct types"
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
    def run(self, **kwargs):
        pass

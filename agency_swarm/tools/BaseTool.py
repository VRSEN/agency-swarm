from abc import ABC, abstractmethod
from typing import Any, ClassVar

from docstring_parser import parse

from pydantic import BaseModel
from agency_swarm.util.shared_state import SharedState


class BaseTool(BaseModel, ABC):
    shared_state: ClassVar[SharedState] = None
    caller_agent: Any = None
    event_handler: Any = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.__class__.shared_state:
            self.__class__.shared_state = SharedState()

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

        properties = schema.get("parameters", {}).get("properties", {})

        properties.pop("caller_agent", None)
        properties.pop("shared_state", None)
        properties.pop("event_handler", None)

        schema["strict"] = cls.ToolConfig.strict
        if cls.ToolConfig.strict:
            schema["parameters"]["additionalProperties"] = False

        required = schema.get("parameters", {}).get("required", [])
        if "caller_agent" in required:
            required.remove("caller_agent")
        if "shared_state" in required:
            required.remove("shared_state")
        if "event_handler" in required:
            required.remove("event_handler")

        return schema

    def model_dump(self, exclude=None, **kwargs):
        if exclude is None:
            exclude = {"caller_agent", "shared_state", "event_handler"}
        else:
            exclude.update({"caller_agent", "shared_state", "event_handler"})
        return super().model_dump(exclude=exclude, **kwargs)

    @abstractmethod
    def run(self, **kwargs):
        pass

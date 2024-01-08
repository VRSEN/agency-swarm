from abc import ABC, abstractmethod
from typing import Optional, Any

from instructor import OpenAISchema

from pydantic import Field


class BaseTool(OpenAISchema, ABC):
    caller_agent: Optional[Any] = Field(
        None, description="The agent that called this tool. Please ignore this field."
    )

    @classmethod
    @property
    def openai_schema(cls):
        # Exclude 'caller_agent' from the properties
        schema = super(BaseTool, cls).openai_schema

        properties = schema.get("parameters", {}).get("properties", {})
        properties.pop("caller_agent", None)

        # If 'caller_agent' is in the required list, remove it
        required = schema.get("parameters", {}).get("required", [])
        if "caller_agent" in required:
            required.remove("caller_agent")

        return schema

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # # Exclude 'run' method from Pydantic model fields
        # self.model_fields.pop("run", None)

    @abstractmethod
    def run(self, **kwargs):
        pass

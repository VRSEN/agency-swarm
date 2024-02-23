from abc import ABC, abstractmethod
from typing import Optional, Any, ClassVar

from instructor import OpenAISchema

from pydantic import Field

class SharedState:
    def __init__(self):
        self.data = {}

    def set(self, key, value):
        if not isinstance(key, str):
            raise ValueError("Key must be a string")
        self.data[key] = value

    def get(self, key, default=None):
        if not isinstance(key, str):
            raise ValueError("Key must be a string")
        return self.data.get(key, default)


class BaseTool(OpenAISchema, ABC):
    shared_state: ClassVar[SharedState] = SharedState()
    caller_agent: Any = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # # Exclude 'run' method from Pydantic model fields
        # self.model_fields.pop("run", None)

    @classmethod
    @property
    def openai_schema(cls):
        # Exclude 'caller_agent' from the properties
        schema = super(BaseTool, cls).openai_schema

        properties = schema.get("parameters", {}).get("properties", {})
        properties.pop("caller_agent", None)
        properties.pop("shared_state", None)

        # If 'caller_agent' is in the required list, remove it
        required = schema.get("parameters", {}).get("required", [])
        if "caller_agent" in required:
            required.remove("caller_agent")
        if "shared_state" in required:
            required.remove("shared_state")

        return schema

    @classmethod
    def openapi_schema(cls, url):
        openai_schema = cls.openai_schema
        defs = {}
        if '$defs' in openai_schema['parameters']:
            defs = openai_schema['parameters']['$defs']
            del openai_schema['parameters']['$defs']

        schema = {
            "openapi": "3.1.0",
            "info": {
                "title": openai_schema['name'],
                "description": openai_schema['description'],
                "version": "v1.0.0"
            },
            "servers": [
                {
                    "url": url,
                }
            ],
            "paths": {},
            "components": {
                "schemas": {},
                "securitySchemes": {
                    "apiKey": {
                        "type": "apiKey"
                    }
                }
            },
        }

        schema['paths']["/" + openai_schema['name']] = {
            "post": {
                "description": openai_schema['description'],
                "operationId": openai_schema['name'],
                "parameters": [],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": openai_schema['parameters']
                        }
                    },
                    "required": True,
                },
                "deprecated": False,
                "security": [
                    {
                        "apiKey": []
                    }
                ],
                "x-openai-isConsequential": False,
            }
        }

        if defs:
            schema['components']['schemas'].update(**defs)

        return schema

    @abstractmethod
    def run(self, **kwargs):
        pass

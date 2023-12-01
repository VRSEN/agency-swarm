from types import MethodType
from typing import Any, Dict
from pydantic import create_model, Field

from .base_tool import BaseTool


class ToolFactory:

    @staticmethod
    def from_langchain_tool(tool):
        """
        Converts a langchain tool into a BaseTool.
        :param tool: A langchain tool.
        :return: A BaseTool.
        """
        try:
            from langchain.tools import format_tool_to_openai_function
        except ImportError:
            raise ImportError("You must install langchain to use this method.")

        def callback(self):
            tool_input = self.model_dump()
            try:
                return tool.run(tool_input)
            except TypeError:
                if len(tool_input) == 1:
                    return tool.run(list(tool_input.values())[0])
                else:
                    raise TypeError(f"Error parsing input for tool '{tool.__class__.__name__}' Please open an issue "
                                    f"on github.")

        return ToolFactory.openai_schema_to_tool(
            format_tool_to_openai_function(tool),
            callback
        )

    @staticmethod
    def openai_schema_to_tool(schema: Dict[str, Any], callback: Any = None):
        """
        Converts an OpenAI schema into a Pydantic model using Pydantic's create_model method.

        Args:
            schema (dict): OpenAI schema in JSON format.
            callback (function): A callback function to be executed when the tool is run.

        Returns:
            PydanticModel: A Pydantic model class.
        """
        # Mapping from JSON schema types to Python types
        type_mapping = {
            'string': str,
            'integer': int,
            'number': float,
            'boolean': bool,
            'array': list,
            'object': dict,
            'null': type(None),
        }

        name = schema['name']
        description = schema['description']
        title = schema['parameters'].get('title', '')
        properties = schema['parameters']['properties']
        required_fields = schema['parameters'].get('required', [])

        # Preparing fields for the Pydantic model
        fields = {}
        private_fields = {}
        for prop, details in properties.items():
            alias = None
            if prop.startswith('_'):
                alias = prop
                prop = prop.lstrip('_')

            json_type = details['type']
            if json_type in type_mapping:
                field_type = type_mapping[json_type]
                field_description = details.get('description', '')
                is_required = prop in required_fields
                field_default = ... if is_required else None
                fields[prop] = (field_type, Field(default=field_default, description=field_description, alias=alias))
            else:
                raise ValueError(f"Unsupported type '{json_type}' for property '{prop}'")

        # Dynamically creating the Pydantic model
        model = create_model(name, **fields)

        print(private_fields)

        tool = type(name, (BaseTool, model), {
            "__doc__": description,
            "run": callback,
        })

        return tool

from typing import Any, Dict, List, Type

from pydantic import create_model, Field

from .base_tool import BaseTool
from ..util.schema import reference_schema


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

        return ToolFactory.from_openai_schema(
            format_tool_to_openai_function(tool),
            callback
        )


    @staticmethod
    def from_openai_schema(schema: Dict[str, Any], callback: Any):
        """
        Converts an OpenAI schema into a BaseTool. Nested propoerties without refs are not supported yet.
        :param schema:
        :param callback:
        :return:
        """
        def resolve_ref(ref: str, defs: Dict[str, Any]) -> Any:
            # Extract the key from the reference
            key = ref.split('/')[-1]
            if key in defs:
                return defs[key]
            else:
                raise ValueError(f"Reference '{ref}' not found in definitions")

        def create_fields(schema: Dict[str, Any], type_mapping: Dict[str, Type[Any]], required_fields: List[str],
                          defs: Dict[str, Any]) -> Dict[str, Any]:
            fields = {}

            for prop, details in schema.items():
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

                    if json_type == 'array':
                        items_schema = details.get('items', {})
                        if 'type' in items_schema:
                            item_type = type_mapping[items_schema['type']]
                            field_type = List[item_type]
                        elif 'properties' in items_schema:  # Handling direct nested object in array
                            nested_properties = items_schema['properties']
                            nested_required = items_schema.get('required', [])
                            nested_model_name = items_schema.get('title', f"{prop}Item")
                            nested_fields = create_fields(nested_properties, type_mapping, nested_required, defs)
                            nested_model = create_model(nested_model_name, **nested_fields)
                            field_type = List[nested_model]
                        elif '$ref' in items_schema:
                            ref_model = resolve_ref(items_schema['$ref'], defs)
                            field_type = List[ref_model]
                        else:
                            raise ValueError("Array items must have a 'type', 'properties', or '$ref'")
                    elif json_type == 'object':
                        if 'properties' in details:
                            nested_properties = details['properties']
                            nested_required = details.get('required', [])
                            nested_model_name = details.get('title', f"{prop}Model")
                            nested_fields = create_fields(nested_properties, type_mapping, nested_required, defs)
                            field_type = create_model(nested_model_name, **nested_fields)
                        elif '$ref' in details:
                            ref_model = resolve_ref(details['$ref'], defs)
                            field_type = ref_model
                        else:
                            raise ValueError("Object must have 'properties' or '$ref'")

                    fields[prop] = (
                    field_type, Field(default=field_default, description=field_description, alias=alias))
                else:
                    raise ValueError(f"Unsupported type '{json_type}' for property '{prop}'")

            return fields

        type_mapping = {
            'string': str,
            'integer': int,
            'number': float,
            'boolean': bool,
            'array': List,
            'object': dict,
            'null': type(None),
        }

        schema = reference_schema(schema)

        name = schema['name']
        description = schema['description']
        properties = schema['parameters']['properties']
        required_fields = schema['parameters'].get('required', [])

        # Add definitions ($defs) to type_mapping
        defs = {k: create_model(k, **create_fields(v['properties'], type_mapping, v.get('required', []), {})) for k, v
                in schema['parameters'].get('$defs', {}).items()}
        type_mapping.update(defs)

        fields = create_fields(properties, type_mapping, required_fields, defs)

        # Dynamically creating the Pydantic model
        model = create_model(name, **fields)

        tool = type(name, (BaseTool, model), {
            "__doc__": description,
            "run": callback,
        })

        return tool



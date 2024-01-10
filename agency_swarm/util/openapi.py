import json
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError
from openapi_spec_validator import validate


def validate_openapi_spec(spec: str):
    spec = json.loads(spec)
    for path, path_item in spec.get('paths', {}).items():
        for operation in path_item.values():
            if 'responses' not in operation:
                operation['responses'] = {'default': {'description': 'Default response'}}
            if 'operationId' not in operation:
                raise ValueError("Operation must contain an operationId")
            if "description" not in operation:
                raise ValueError("Operation must contain a description")
            if "parameters" not in operation:
                operation["parameters"] = []
    validate(spec)

    return spec
import json


def validate_openapi_spec(spec: str):
    spec = json.loads(spec)

    # Validate that 'paths' is present in the spec
    if 'paths' not in spec:
        raise ValueError("The spec must contain 'paths'.")

    for path, path_item in spec['paths'].items():
        # Ensure each path item is a dictionary
        if not isinstance(path_item, dict):
            raise ValueError(f"Path item for '{path}' must be a dictionary.")

        for operation in path_item.values():
            # Basic validation for each operation
            if 'operationId' not in operation:
                raise ValueError("Each operation must contain an 'operationId'.")
            if 'description' not in operation:
                raise ValueError("Each operation must contain a 'description'.")

    # Perform any additional basic validation as needed

    # If the function reaches this point, the spec has passed basic validation
    return spec
from typing import Dict, Any


def dereference_schema(schema):
    defs = schema.get("parameters", {}).get("$defs", {})

    def resolve_refs(node):
        if isinstance(node, dict):
            if '$ref' in node:
                ref_path = node['$ref']
                ref_path_parts = ref_path.split('/')
                ref = defs.get(ref_path_parts[-1], {})
                return ref
            else:
                return {k: resolve_refs(v) for k, v in node.items()}
        elif isinstance(node, list):
            return [resolve_refs(element) for element in node]
        else:
            return node

    return resolve_refs(schema)


def reference_schema(schema):
    # Enhanced function to only extract nested properties into $defs

    def find_and_extract_defs(node, defs, parent_key=None, path_prefix="#/$defs/"):
        if isinstance(node, dict):
            # Extract nested properties into $defs
            if parent_key == 'properties' and 'properties' in node and isinstance(node['properties'], dict):
                def_name = node.get('title', None)
                if def_name:
                    defs[def_name] = node
                    return {"$ref": path_prefix + def_name}

            # Recursively process the dictionary
            return {k: find_and_extract_defs(v, defs, parent_key=k) for k, v in node.items()}
        elif isinstance(node, list):
            # Recursively process the list
            return [find_and_extract_defs(element, defs, parent_key) for element in node]
        else:
            return node

    defs = {}
    # Extract definitions and update the schema
    new_schema = {k: find_and_extract_defs(v, defs) for k, v in schema.items()}
    if defs:
        new_schema['parameters'] = new_schema.get('parameters', {})
        new_schema['parameters']['$defs'] = defs
    return new_schema




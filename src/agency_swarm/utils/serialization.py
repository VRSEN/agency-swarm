"""Serialization utilities for converting objects to JSON-compatible formats."""

import dataclasses
from typing import Any

from pydantic import BaseModel


def serialize(obj: Any, _visited: set[int] | None = None, string_output: bool = True) -> Any:
    """
    Convert any object to a JSON-compatible format.

    Args:
        obj: Object to serialize
        _visited: Set of already-visited object IDs for circular reference detection (internal use)
        string_output: If True, convert primitives to strings; if False, preserve primitive types

    Returns:
        JSON-serializable representation of the object
    """
    if _visited is None:
        _visited = set()

    # Check for circular references
    obj_id = id(obj)
    if obj_id in _visited:
        # Always stringify circular refs to prevent JSON serialization errors
        return str(obj)

    if dataclasses.is_dataclass(obj):
        _visited.add(obj_id)
        # Use __dict__ to preserve dynamically added attributes like agent and callerAgent
        result = {k: serialize(v, _visited, string_output) for k, v in obj.__dict__.items() if not k.startswith("_")}
        _visited.discard(obj_id)
        return result
    elif isinstance(obj, BaseModel):
        return {k: serialize(v, _visited, string_output) for k, v in obj.model_dump().items()}
    elif isinstance(obj, list | tuple):
        return [serialize(item, _visited, string_output) for item in obj]
    elif isinstance(obj, dict):
        return {k: serialize(v, _visited, string_output) for k, v in obj.items()}
    elif hasattr(obj, "__dict__") and not isinstance(obj, type):
        # Handle any object with __dict__ (regular dynamic objects)
        # This ensures circular reference tracking for all objects with attributes
        _visited.add(obj_id)
        result = {k: serialize(v, _visited, string_output) for k, v in obj.__dict__.items() if not k.startswith("_")}
        _visited.discard(obj_id)
        return result
    else:
        if string_output:
            return str(obj)
        else:
            return obj

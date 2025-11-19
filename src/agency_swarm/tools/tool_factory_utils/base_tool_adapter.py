from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import cast

from agents import FunctionTool
from agents.exceptions import ModelBehaviorError
from agents.strict_schema import ensure_strict_json_schema
from agents.tool import default_tool_error_function
from pydantic import ValidationError
from pydantic_core import InitErrorDetails

from agency_swarm.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)


def adapt_base_tool(base_tool: type[BaseTool]) -> FunctionTool:
    """
    Adapts a BaseTool (class-based) to a FunctionTool (function-based).
    """
    name = base_tool.__name__
    description = base_tool.__doc__ or ""
    if bool(getattr(base_tool, "__abstractmethods__", set())):
        raise TypeError(f"BaseTool '{name}' must implement all abstract methods.")
    if description == "":
        logger.warning("Warning: Tool %s has no docstring.", name)

    params_json_schema = base_tool.model_json_schema()
    if getattr(base_tool.ToolConfig, "strict", False):
        params_json_schema = ensure_strict_json_schema(params_json_schema)
    params_json_schema = {k: v for k, v in params_json_schema.items() if k not in ("title", "description")}
    params_json_schema["additionalProperties"] = False

    async def on_invoke_tool(ctx, input_json: str):
        try:
            args = json.loads(input_json) if input_json else {}
        except Exception as e:  # pragma: no cover - defensive guard
            return f"Error: Invalid JSON input: {e}"
        try:
            tool_instance = base_tool(**args)
            if ctx is not None:
                tool_instance._context = ctx
            if inspect.iscoroutinefunction(tool_instance.run):
                return await tool_instance.run()
            return await asyncio.to_thread(tool_instance.run)
        except ValidationError as e:
            formatted_msg = _format_value_error(e)
            if formatted_msg is not None:
                return default_tool_error_function(ctx, ValueError(formatted_msg))
            errors = e.errors()
            non_value_errors = [err for err in errors if err.get("type") != "value_error"]
            line_errors = cast(list[InitErrorDetails], non_value_errors or errors)
            rewritten_error = ValidationError.from_exception_data(f"{name}_args", line_errors)
            model_error = ModelBehaviorError(f"Invalid JSON input for tool {name}: {rewritten_error}")
            return default_tool_error_function(ctx, model_error)
        except Exception as e:
            return default_tool_error_function(ctx, e)

    func_tool = FunctionTool(
        name=name,
        description=description.strip(),
        params_json_schema=params_json_schema,
        on_invoke_tool=on_invoke_tool,
        strict_json_schema=getattr(base_tool.ToolConfig, "strict", False) or False,
    )
    if hasattr(base_tool.ToolConfig, "one_call_at_a_time"):
        func_tool.one_call_at_a_time = bool(base_tool.ToolConfig.one_call_at_a_time)  # type: ignore[attr-defined]
    return func_tool


def _format_value_error(validation_error: ValidationError) -> str | None:
    """
    Extract a user-facing message when every failure comes from value validators.
    """
    errors = validation_error.errors()
    if not errors:
        return None
    if any(err.get("type") != "value_error" for err in errors):
        return None

    def _message_from_error(error: InitErrorDetails) -> str:
        ctx_error = error.get("ctx", {}).get("error")
        if ctx_error is not None:
            return str(ctx_error)
        return cast(str, error.get("msg", "Invalid value"))

    if len(errors) == 1:
        return _message_from_error(cast(InitErrorDetails, errors[0]))

    combined_messages: list[str] = []
    for error in cast(list[InitErrorDetails], errors):
        message = _message_from_error(error)
        loc = error.get("loc") or ()
        loc_string = ".".join(str(part) for part in loc if part != "__root__")
        if loc_string:
            combined_messages.append(f"{loc_string}: {message}")
        else:
            combined_messages.append(message)
    return "; ".join(combined_messages)

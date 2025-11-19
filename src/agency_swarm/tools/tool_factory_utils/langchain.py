from __future__ import annotations

import inspect
import json

from agents import FunctionTool


def from_langchain_tools(tools: list) -> list[FunctionTool]:
    """
    Converts a list of langchain tools into a list of FunctionTools.
    """
    converted_tools = []
    for tool in tools:
        converted_tools.append(from_langchain_tool(tool))
    return converted_tools


def from_langchain_tool(tool) -> FunctionTool:
    """
    Converts a langchain tool into a FunctionTool.
    """
    try:
        from langchain_community.tools import format_tool_to_openai_function
    except ImportError as e:  # pragma: no cover - import guard
        raise ImportError("You must install langchain to use this method.") from e

    if inspect.isclass(tool):
        tool = tool()

    # Get the OpenAI function schema from langchain tool
    openai_schema = format_tool_to_openai_function(tool)

    # Extract tool information
    tool_name = openai_schema.get("name", tool.__class__.__name__)
    tool_description = openai_schema.get("description", tool.description)

    # Get parameters schema - this should be the full JSON schema for the FunctionTool
    parameters_schema = openai_schema.get("parameters", {})

    # Ensure proper schema structure for FunctionTool
    if not parameters_schema:
        parameters_schema = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}

    async def on_invoke_tool(ctx, input_json: str):
        """Callback function that executes the langchain tool."""
        try:
            args = json.loads(input_json) if input_json else {}
        except Exception as e:  # pragma: no cover - defensive guard
            return f"Error: Invalid JSON input: {e}"
        try:
            result = tool.run(args)
            return result
        except TypeError:
            if len(args) == 1:
                result = tool.run(list(args.values())[0])
                return result
            return f"Error parsing input for tool '{tool.__class__.__name__}'. Please open an issue on github."
        except Exception as e:  # pragma: no cover - passthrough
            return f"Error running LangChain tool: {e}"

    func_tool = FunctionTool(
        name=tool_name,
        description=tool_description.strip(),
        params_json_schema=parameters_schema,
        on_invoke_tool=on_invoke_tool,
        strict_json_schema=False,  # LangChain tools are not strict by default
    )
    return func_tool

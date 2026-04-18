from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, overload

from agents import FunctionTool, RunContextWrapper, function_tool as sdk_function_tool
from agents.tool_context import ToolContext

_MANUAL_TOOL_CALL_ID_TEMPLATE = "agency_swarm_manual_{tool_name}"
_WRAPPED_ATTR = "_agency_swarm_manual_tool_context_compat"


def build_manual_tool_context(
    ctx: Any,
    *,
    tool_name: str,
    input_json: str,
) -> ToolContext[Any]:
    tool_call_id = _MANUAL_TOOL_CALL_ID_TEMPLATE.format(tool_name=tool_name)
    if isinstance(ctx, ToolContext):
        return ctx
    if isinstance(ctx, RunContextWrapper):
        return ToolContext.from_agent_context(
            ctx,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_arguments=input_json,
        )
    return ToolContext(
        context=ctx,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        tool_arguments=input_json,
    )


def normalize_function_tool(tool: FunctionTool) -> FunctionTool:
    """Make direct/manual tool invocation behave like pre-0.14 SDK releases."""
    if getattr(tool, _WRAPPED_ATTR, False):
        return tool

    original_on_invoke_tool = tool.on_invoke_tool

    @wraps(original_on_invoke_tool)
    async def on_invoke_tool(ctx: Any, input_json: str) -> Any:
        manual_context = build_manual_tool_context(
            ctx,
            tool_name=tool.name,
            input_json=input_json,
        )
        return await original_on_invoke_tool(manual_context, input_json)

    on_invoke_tool.__dict__.update(getattr(original_on_invoke_tool, "__dict__", {}))
    tool.on_invoke_tool = on_invoke_tool
    setattr(tool, _WRAPPED_ATTR, True)
    return tool


@overload
def function_tool(
    func: Callable[..., Any],
    *,
    name_override: str | None = None,
    description_override: str | None = None,
    docstring_style: str | None = None,
    use_docstring_info: bool = True,
    failure_error_function: Callable[..., Any] | None = None,
    strict_mode: bool = True,
    is_enabled: bool | Callable[..., Any] = True,
    needs_approval: bool | Callable[..., Awaitable[bool]] = False,
    tool_input_guardrails: list[Any] | None = None,
    tool_output_guardrails: list[Any] | None = None,
    timeout: float | None = None,
    timeout_behavior: str = "error_as_result",
    timeout_error_function: Callable[..., Any] | None = None,
    defer_loading: bool = False,
) -> FunctionTool: ...


@overload
def function_tool(
    *,
    name_override: str | None = None,
    description_override: str | None = None,
    docstring_style: str | None = None,
    use_docstring_info: bool = True,
    failure_error_function: Callable[..., Any] | None = None,
    strict_mode: bool = True,
    is_enabled: bool | Callable[..., Any] = True,
    needs_approval: bool | Callable[..., Awaitable[bool]] = False,
    tool_input_guardrails: list[Any] | None = None,
    tool_output_guardrails: list[Any] | None = None,
    timeout: float | None = None,
    timeout_behavior: str = "error_as_result",
    timeout_error_function: Callable[..., Any] | None = None,
    defer_loading: bool = False,
) -> Callable[[Callable[..., Any]], FunctionTool]: ...


def function_tool(
    func: Callable[..., Any] | None = None,
    **kwargs: Any,
) -> FunctionTool | Callable[[Callable[..., Any]], FunctionTool]:
    """Wrap the SDK decorator so manual invocation still works outside Runner."""
    if func is not None:
        return normalize_function_tool(sdk_function_tool(func, **kwargs))

    decorator = sdk_function_tool(**kwargs)

    @wraps(decorator)
    def wrapped(real_func: Callable[..., Any]) -> FunctionTool:
        return normalize_function_tool(decorator(real_func))

    return wrapped

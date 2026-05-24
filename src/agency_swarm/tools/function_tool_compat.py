from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, fields
from functools import wraps
from typing import Any, cast, get_origin, overload

from agents import FunctionTool, RunContextWrapper, function_tool as sdk_function_tool
from agents.tool_context import ToolContext

_MANUAL_TOOL_CALL_ID_TEMPLATE = "agency_swarm_manual_{tool_name}"
_WRAPPED_ATTR = "_agency_swarm_manual_tool_context_compat"
_ORIGINAL_INVOKER_ATTR = "_agency_swarm_original_on_invoke_tool"


@dataclass
class _ManualContextFunctionTool(FunctionTool):
    """FunctionTool variant whose copied instances bind manual context to themselves."""

    _agency_original_on_invoke_tool: Callable[[Any, str], Awaitable[Any]] | None = field(
        default=None,
        repr=False,
    )
    _agency_expects_run_context_wrapper: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self._agency_original_on_invoke_tool is not None:
            bind_to_tool = getattr(self._agency_original_on_invoke_tool, "__agents_bind_function_tool__", None)
            if callable(bind_to_tool):
                self._agency_original_on_invoke_tool = cast(Callable[[Any, str], Awaitable[Any]], bind_to_tool(self))
            self.on_invoke_tool = self._invoke_with_manual_context
            setattr(self, _WRAPPED_ATTR, True)

    async def _invoke_with_manual_context(self, ctx: Any, input: str) -> Any:
        original_on_invoke_tool = self._agency_original_on_invoke_tool
        if original_on_invoke_tool is None:
            raise RuntimeError("Missing original FunctionTool invoker")
        if self._agency_expects_run_context_wrapper and isinstance(ctx, RunContextWrapper):
            return await original_on_invoke_tool(ctx, input)

        manual_context = build_manual_tool_context(
            ctx,
            tool_name=self.name,
            tool_namespace=getattr(self, "_tool_namespace", None),
            input_json=input,
        )
        return await original_on_invoke_tool(manual_context, input)


def build_manual_tool_context(
    ctx: Any,
    *,
    tool_name: str,
    tool_namespace: str | None = None,
    input_json: str,
) -> ToolContext[Any]:
    tool_call_id = _MANUAL_TOOL_CALL_ID_TEMPLATE.format(tool_name=tool_name)
    if isinstance(ctx, ToolContext):
        context_namespace_matches = ctx.tool_namespace == tool_namespace or (
            tool_namespace is None and ctx.tool_namespace == tool_name
        )
        if ctx.tool_name == tool_name and context_namespace_matches and ctx.tool_arguments == input_json:
            return ctx
        return ToolContext.from_agent_context(
            ctx,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_namespace=tool_namespace,
            tool_arguments=input_json,
        )
    if isinstance(ctx, RunContextWrapper):
        return ToolContext.from_agent_context(
            ctx,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_namespace=tool_namespace,
            tool_arguments=input_json,
        )
    return ToolContext(
        context=ctx,
        tool_name=tool_name,
        tool_namespace=tool_namespace,
        tool_call_id=tool_call_id,
        tool_arguments=input_json,
    )


def normalize_function_tool(tool: FunctionTool) -> FunctionTool:
    """Keep direct/manual FunctionTool calls compatible with openai-agents 0.14."""
    if isinstance(tool, _ManualContextFunctionTool) and tool._agency_original_on_invoke_tool is not None:
        return tool

    original_on_invoke_attr = getattr(tool, "on_invoke_tool", None)
    if not callable(original_on_invoke_attr):
        return tool

    if getattr(tool, "_is_agent_tool", False):
        return tool

    previous_original = getattr(original_on_invoke_attr, _ORIGINAL_INVOKER_ATTR, None)
    if getattr(tool, _WRAPPED_ATTR, False) and previous_original is None:
        return tool
    if previous_original is None and not _is_sdk_function_tool(tool):
        return tool

    original_on_invoke_tool = cast(
        Callable[[Any, str], Awaitable[Any]],
        previous_original or original_on_invoke_attr,
    )
    expects_run_context_wrapper = _expects_run_context_wrapper(original_on_invoke_tool)
    tool_kwargs = {tool_field.name: getattr(tool, tool_field.name) for tool_field in fields(FunctionTool)}
    tool_kwargs["on_invoke_tool"] = original_on_invoke_tool
    wrapped_tool = _ManualContextFunctionTool(
        **tool_kwargs,
        _agency_original_on_invoke_tool=original_on_invoke_tool,
        _agency_expects_run_context_wrapper=expects_run_context_wrapper,
    )
    _copy_internal_tool_state(tool, wrapped_tool)
    return wrapped_tool


def _copy_internal_tool_state(source: FunctionTool, target: FunctionTool) -> None:
    field_names = {tool_field.name for tool_field in fields(target)}
    for attr_name, attr_value in getattr(source, "__dict__", {}).items():
        if attr_name not in field_names and attr_name != _WRAPPED_ATTR:
            setattr(target, attr_name, attr_value)

    for attr_name in ("_is_agent_tool", "_is_codex_tool", "_agent_instance"):
        if hasattr(source, attr_name):
            setattr(target, attr_name, getattr(source, attr_name))


def _is_sdk_function_tool(tool: FunctionTool) -> bool:
    """Detect tools built by the SDK @function_tool decorator without importing private types."""
    on_invoke_tool = getattr(tool, "on_invoke_tool", None)
    return getattr(on_invoke_tool, "_function_tool", None) is tool and callable(
        getattr(on_invoke_tool, "_invoke_tool_impl", None)
    )


def _expects_run_context_wrapper(func: Callable[..., Any]) -> bool:
    try:
        first_param = next(iter(inspect.signature(func).parameters.values()))
    except (StopIteration, TypeError, ValueError):
        return False

    annotation = first_param.annotation
    if annotation is inspect.Signature.empty:
        return False
    if annotation is RunContextWrapper or get_origin(annotation) is RunContextWrapper:
        return True
    if isinstance(annotation, str):
        return annotation == "RunContextWrapper" or annotation.startswith("RunContextWrapper[")
    return False


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

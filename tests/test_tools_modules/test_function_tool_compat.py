import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agents import (
    Agent as SDKAgent,
    FunctionTool,
    RunConfig,
    RunContextWrapper,
    _debug,
    function_tool as sdk_function_tool,
    tool_namespace,
)
from agents.exceptions import MCPToolCancellationError
from agents.run_config import ToolErrorFormatterArgs
from agents.tool_context import ToolContext
from pydantic import BaseModel

from agency_swarm import Agent, BaseTool, function_tool
from agency_swarm.tools.function_tool_compat import tool_error_with_details
from agency_swarm.tools.tool_factory import ToolFactory


@pytest.mark.asyncio
async def test_sdk_function_tool_accepts_manual_run_context_wrapper() -> None:
    """SDK @function_tool instances should accept direct RunContextWrapper calls."""
    seen_contexts: list[ToolContext[dict[str, str]]] = []

    @sdk_function_tool
    async def sdk_context_tool(ctx: RunContextWrapper[dict[str, str]], value: str) -> str:
        tool_context = cast(ToolContext[dict[str, str]], ctx)
        seen_contexts.append(tool_context)
        return f"{tool_context.context['label']}:{value}:{tool_context.tool_name}:{tool_context.tool_arguments}"

    wrapper = RunContextWrapper(context={"label": "agency"})
    agent = Agent(name="test", instructions="test", tools=[sdk_context_tool])
    tool = agent.tools[0]
    assert isinstance(tool, FunctionTool)
    on_invoke_tool = cast(Any, tool.on_invoke_tool)

    result = await on_invoke_tool(wrapper, '{"value":"ping"}')

    assert result == 'agency:ping:sdk_context_tool:{"value":"ping"}'
    assert len(seen_contexts) == 1
    assert isinstance(seen_contexts[0], ToolContext)
    assert seen_contexts[0].context is wrapper.context


@pytest.mark.asyncio
async def test_agency_function_tool_accepts_keyword_input_and_manual_context() -> None:
    """agency_swarm.function_tool instances should accept direct positional and keyword input calls."""
    seen_contexts: list[ToolContext[dict[str, str] | None]] = []

    @function_tool
    async def agency_context_tool(ctx: RunContextWrapper[dict[str, str] | None], x: int) -> str:
        tool_context = cast(ToolContext[dict[str, str] | None], ctx)
        seen_contexts.append(tool_context)
        context_label = "none" if tool_context.context is None else tool_context.context["label"]
        return f"{context_label}:{x}:{tool_context.tool_name}:{tool_context.tool_arguments}"

    on_invoke_tool = cast(Any, agency_context_tool.on_invoke_tool)

    keyword_result = await on_invoke_tool(ctx=None, input='{"x":1}')
    positional_result = await on_invoke_tool({"label": "manual"}, '{"x":2}')

    assert keyword_result == 'none:1:agency_context_tool:{"x":1}'
    assert positional_result == 'manual:2:agency_context_tool:{"x":2}'
    assert len(seen_contexts) == 2
    assert all(isinstance(seen_context, ToolContext) for seen_context in seen_contexts)
    assert [seen_context.context for seen_context in seen_contexts] == [
        None,
        {"label": "manual"},
    ]
    assert [seen_context.tool_arguments for seen_context in seen_contexts] == [
        '{"x":1}',
        '{"x":2}',
    ]


@pytest.mark.asyncio
async def test_agency_function_tool_rebuilds_forwarded_tool_context_for_new_tool() -> None:
    """Forwarded ToolContext should describe the callee, not the caller."""
    seen_contexts: list[ToolContext[dict[str, str]]] = []

    @function_tool
    async def callee_tool(ctx: RunContextWrapper[dict[str, str]], value: str) -> str:
        tool_context = cast(ToolContext[dict[str, str]], ctx)
        seen_contexts.append(tool_context)
        return f"{tool_context.context['label']}:{value}:{tool_context.tool_name}:{tool_context.tool_arguments}"

    caller_context = ToolContext(
        context={"label": "agency"},
        tool_name="caller_tool",
        tool_call_id="caller_call",
        tool_arguments='{"value":"old"}',
    )
    on_invoke_tool = cast(Any, callee_tool.on_invoke_tool)

    result = await on_invoke_tool(caller_context, '{"value":"new"}')

    assert result == 'agency:new:callee_tool:{"value":"new"}'
    assert len(seen_contexts) == 1
    assert seen_contexts[0] is not caller_context
    assert seen_contexts[0].context is caller_context.context
    assert seen_contexts[0].tool_name == "callee_tool"
    assert seen_contexts[0].tool_arguments == '{"value":"new"}'
    assert seen_contexts[0].tool_call_id == "agency_swarm_manual_callee_tool"


@pytest.mark.asyncio
async def test_copied_agency_function_tool_rebinds_manual_context_to_copy_name() -> None:
    """Copied FunctionTool instances should describe the copied tool."""
    seen_contexts: list[ToolContext[dict[str, str]]] = []

    @function_tool
    async def original_tool(ctx: RunContextWrapper[dict[str, str]], value: str) -> str:
        tool_context = cast(ToolContext[dict[str, str]], ctx)
        seen_contexts.append(tool_context)
        return f"{tool_context.context['label']}:{value}:{tool_context.tool_name}:{tool_context.tool_call_id}"

    copied_tool = replace(original_tool, name="copied_tool")
    on_invoke_tool = cast(Any, copied_tool.on_invoke_tool)

    result = await on_invoke_tool(RunContextWrapper(context={"label": "agency"}), '{"value":"new"}')

    assert result == "agency:new:copied_tool:agency_swarm_manual_copied_tool"
    assert len(seen_contexts) == 1
    assert seen_contexts[0].tool_name == "copied_tool"
    assert seen_contexts[0].tool_call_id == "agency_swarm_manual_copied_tool"


@pytest.mark.asyncio
async def test_copied_agency_function_tool_rebinds_failure_handler_to_copy() -> None:
    """Copied FunctionTool failure handlers should resolve against the copied tool."""

    def failure_message(ctx: ToolContext[None], error: Exception) -> str:
        return f"{ctx.tool_name}:{error}"

    @function_tool(failure_error_function=failure_message)
    async def original_tool(ctx: RunContextWrapper[None], value: str) -> str:  # noqa: ARG001
        raise RuntimeError("boom")

    copied_tool = replace(original_tool, name="copied_tool")
    on_invoke_tool = cast(Any, copied_tool.on_invoke_tool)

    result = await on_invoke_tool(RunContextWrapper(context=None), '{"value":"new"}')

    assert result == "copied_tool:boom"


def test_agency_function_tool_preserves_deferred_namespace_metadata() -> None:
    """Wrapped FunctionTool instances should keep SDK loading metadata."""

    @function_tool(defer_loading=True)
    def deferred_tool(value: str) -> str:
        return value

    namespaced_tool = tool_namespace(name="demo_namespace", description="Demo namespace", tools=[deferred_tool])[0]
    agent = Agent(name="test", instructions="test", tools=[namespaced_tool])
    tool = agent.tools[0]

    assert isinstance(tool, FunctionTool)
    assert tool.defer_loading is True
    assert tool._tool_namespace == "demo_namespace"
    assert tool._tool_namespace_description == "Demo namespace"


@pytest.mark.asyncio
async def test_deferred_agency_function_tool_keeps_sdk_tool_context_metadata() -> None:
    """Deferred top-level tools can use the SDK synthetic namespace for real calls."""
    seen_contexts: list[ToolContext[dict[str, str]]] = []

    @function_tool(defer_loading=True)
    async def deferred_tool(ctx: RunContextWrapper[dict[str, str]], value: str) -> str:
        tool_context = cast(ToolContext[dict[str, str]], ctx)
        seen_contexts.append(tool_context)
        return f"{tool_context.tool_call_id}:{value}"

    sdk_context = ToolContext(
        context={"label": "agency"},
        tool_name="deferred_tool",
        tool_namespace="deferred_tool",
        tool_call_id="call_real",
        tool_arguments='{"value":"new"}',
    )
    on_invoke_tool = cast(Any, deferred_tool.on_invoke_tool)

    result = await on_invoke_tool(sdk_context, '{"value":"new"}')

    assert result == "call_real:new"
    assert len(seen_contexts) == 1
    assert seen_contexts[0] is sdk_context


@pytest.mark.asyncio
async def test_namespaced_agency_function_tool_manual_context_keeps_namespace() -> None:
    """Manual ToolContext should preserve SDK namespace identity."""
    seen_contexts: list[ToolContext[dict[str, str]]] = []

    @function_tool
    async def namespaced_tool(ctx: RunContextWrapper[dict[str, str]], value: str) -> str:
        tool_context = cast(ToolContext[dict[str, str]], ctx)
        seen_contexts.append(tool_context)
        return f"{tool_context.qualified_tool_name}:{tool_context.context['label']}:{value}"

    namespaced = tool_namespace(name="demo_namespace", description="Demo namespace", tools=[namespaced_tool])[0]
    agent = Agent(name="test", instructions="test", tools=[namespaced])
    tool = agent.tools[0]
    assert isinstance(tool, FunctionTool)
    on_invoke_tool = cast(Any, tool.on_invoke_tool)

    result = await on_invoke_tool(RunContextWrapper(context={"label": "agency"}), '{"value":"new"}')

    assert result == "demo_namespace.namespaced_tool:agency:new"
    assert len(seen_contexts) == 1
    assert seen_contexts[0].tool_name == "namespaced_tool"
    assert seen_contexts[0].tool_namespace == "demo_namespace"
    assert seen_contexts[0].qualified_tool_name == "demo_namespace.namespaced_tool"


def test_sdk_agent_tool_is_not_rewrapped_as_decorator_function_tool() -> None:
    """Agent.as_tool() should keep the SDK's own invoker."""
    nested_agent = SDKAgent(name="nested", instructions="Return the input.")
    nested_tool = nested_agent.as_tool(tool_name="nested_tool", tool_description="Nested tool")

    agent = Agent(name="test", instructions="test", tools=[nested_tool])
    tool = agent.tools[0]

    assert isinstance(tool, FunctionTool)
    assert tool._is_agent_tool is True
    assert getattr(tool, "_agency_swarm_manual_tool_context_compat", False) is False
    assert not hasattr(tool, "_agency_original_on_invoke_tool")


@pytest.mark.asyncio
async def test_manual_function_tool_receives_original_context_unchanged() -> None:
    """Manual FunctionTool callbacks should keep the exact caller-provided context."""
    seen_contexts: list[object] = []

    async def invoke(ctx: object, input_json: str) -> str:
        seen_contexts.append(ctx)
        return input_json

    tool = FunctionTool(
        name="manual_context_tool",
        description="manual context tool",
        params_json_schema={"type": "object", "properties": {}},
        on_invoke_tool=invoke,
        strict_json_schema=False,
    )
    original_context = SimpleNamespace(marker="original")
    agent = Agent(name="test", instructions="test", tools=[tool])
    agent_tool = agent.tools[0]
    assert isinstance(agent_tool, FunctionTool)
    on_invoke_tool = cast(Any, agent_tool.on_invoke_tool)

    result = await on_invoke_tool(original_context, '{"value":"pong"}')

    assert result == '{"value":"pong"}'
    assert len(seen_contexts) == 1
    assert seen_contexts[0] is original_context
    assert not isinstance(seen_contexts[0], ToolContext)


@pytest.mark.asyncio
async def test_function_tool_error_reaches_model_with_details_and_honors_override() -> None:
    """Exception text reaches the model by default; explicit failure_error_function still wins."""

    @function_tool
    def failing_tool(value: int) -> str:
        raise ValueError(f"value {value} is out of range")

    @function_tool(failure_error_function=lambda ctx, error: "custom failure")
    def custom_failing_tool(value: int) -> str:
        raise ValueError("hidden")

    default_result = await failing_tool.on_invoke_tool(cast(Any, None), '{"value": 7}')
    custom_result = await custom_failing_tool.on_invoke_tool(cast(Any, None), '{"value": 7}')

    assert (
        default_result == "An error occurred while running the tool. Please try again. Error: value 7 is out of range"
    )
    assert custom_result == "custom failure"


@pytest.mark.asyncio
async def test_function_tool_and_base_tool_honor_run_config_tool_error_formatter() -> None:
    """RunConfig.tool_error_formatter formats failures for both function_tool and BaseTool."""
    seen_args: list[ToolErrorFormatterArgs[Any]] = []

    async def async_formatter(args: ToolErrorFormatterArgs[Any]) -> str:
        seen_args.append(args)
        return f"FORMATTED[{args.kind}:{args.tool_name}]: {args.error}"

    @function_tool
    def failing_func(value: int) -> str:
        raise ValueError(f"bad value {value}")

    class FailingBaseTool(BaseTool):
        """Tool that fails with a known validation error."""

        value: int

        def run(self) -> str:
            raise ValueError(f"base bad value {self.value}")

    adapted_base_tool = ToolFactory.adapt_base_tool(FailingBaseTool)

    func_ctx = ToolContext(
        context=None,
        tool_name="failing_func",
        tool_call_id="call_func",
        tool_arguments='{"value": 3}',
        run_config=RunConfig(tool_error_formatter=async_formatter),
    )
    base_ctx = ToolContext(
        context=None,
        tool_name="FailingBaseTool",
        tool_call_id="call_base",
        tool_arguments='{"value": 4}',
        run_config=RunConfig(tool_error_formatter=async_formatter),
    )

    func_result = await failing_func.on_invoke_tool(func_ctx, '{"value": 3}')
    base_result = await adapted_base_tool.on_invoke_tool(base_ctx, '{"value": 4}')

    assert func_result == "FORMATTED[tool_exception:failing_func]: bad value 3"
    assert base_result == "FORMATTED[tool_exception:FailingBaseTool]: base bad value 4"
    assert [arg.call_id for arg in seen_args] == ["call_func", "call_base"]

    # Returning None from the formatter falls back to Agency Swarm's detailed default message.
    fallback_ctx = ToolContext(
        context=None,
        tool_name="failing_func",
        tool_call_id="call_fallback",
        tool_arguments='{"value": 9}',
        run_config=RunConfig(tool_error_formatter=lambda _args: None),
    )
    fallback_result = await failing_func.on_invoke_tool(fallback_ctx, '{"value": 9}')
    assert fallback_result == "An error occurred while running the tool. Please try again. Error: bad value 9"


@pytest.mark.asyncio
async def test_function_tool_invalid_json_returns_parse_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed JSON arguments tell the model to retry with valid JSON."""

    @function_tool
    def add(x: int) -> int:
        return x + 1

    monkeypatch.setattr(_debug, "DONT_LOG_TOOL_DATA", False)
    result = await add.on_invoke_tool(cast(Any, None), "{not json")
    assert "An error occurred while parsing tool arguments. Please try again with valid JSON." in result
    assert "Invalid JSON input for tool add" in result

    monkeypatch.setattr(_debug, "DONT_LOG_TOOL_DATA", True)
    redacted_result = await add.on_invoke_tool(cast(Any, None), "{secret_payload")
    assert "An error occurred while parsing tool arguments. Please try again with valid JSON." in redacted_result
    assert "secret_payload" not in redacted_result


@pytest.mark.asyncio
async def test_tool_body_json_decode_error_is_reported_as_tool_run_error() -> None:
    """A JSONDecodeError raised inside a tool body must not be mislabeled as bad tool arguments."""

    @function_tool
    def parse_file(path: str) -> str:
        json.loads("{broken file content")
        return path

    result = await parse_file.on_invoke_tool(cast(Any, None), '{"path": "config.json"}')
    assert result.startswith("An error occurred while running the tool. Please try again. Error:")
    assert "parsing tool arguments" not in result


@pytest.mark.asyncio
async def test_output_type_function_tool_keeps_sdk_default_failure_policy() -> None:
    """Tools with output_type keep SDK default failure handling so output-schema bypass stays intact."""

    class TypedOut(BaseModel):
        value: int

    @function_tool(output_type=TypedOut)
    def typed_tool(x: int) -> TypedOut:
        raise ValueError(f"boom {x}")

    assert typed_tool._use_default_failure_error_function is True
    ctx = ToolContext(
        context=None,
        tool_name="typed_tool",
        tool_call_id="call_typed",
        tool_arguments='{"x": 1}',
    )
    result = await typed_tool.on_invoke_tool(ctx, '{"x": 1}')
    assert result == "An error occurred while running the tool."
    assert getattr(ctx, "_function_tool_default_failure_handled", False) is True


@pytest.mark.asyncio
async def test_base_tool_invalid_json_formatter_and_tool_error_fallback_paths() -> None:
    """BaseTool invalid JSON honors RunConfig.tool_error_formatter and fallbacks handle edge cases."""

    class JsonTool(BaseTool):
        """Simple tool for invalid JSON formatter coverage."""

        value: int

        def run(self) -> str:
            return str(self.value)

    adapted = ToolFactory.adapt_base_tool(JsonTool)
    ctx = ToolContext(
        context=None,
        tool_name="JsonTool",
        tool_call_id="call_json",
        tool_arguments="{bad",
        run_config=RunConfig(tool_error_formatter=lambda args: f"FMT[{args.kind}:{args.tool_name}]"),
    )
    assert await adapted.on_invoke_tool(ctx, "{bad") == "FMT[tool_exception:JsonTool]"

    # Formatter raising an error or returning a non-string falls back to detailed default text.
    def raising_formatter(_args: ToolErrorFormatterArgs[Any]) -> str:
        raise RuntimeError("formatter exploded")

    raising_ctx = ToolContext(
        context=None,
        tool_name="JsonTool",
        tool_call_id="call_raise",
        tool_arguments="{}",
        run_config=RunConfig(tool_error_formatter=raising_formatter),
    )
    assert await tool_error_with_details(raising_ctx, ValueError("inner")) == (
        "An error occurred while running the tool. Please try again. Error: inner"
    )

    non_str_ctx = ToolContext(
        context=None,
        tool_name="JsonTool",
        tool_call_id="call_nonstr",
        tool_arguments="{}",
        run_config=RunConfig(tool_error_formatter=cast(Any, lambda _args: 123)),
    )
    assert await tool_error_with_details(non_str_ctx, ValueError("inner")) == (
        "An error occurred while running the tool. Please try again. Error: inner"
    )

    # MCPToolCancellationError bypasses tool_error_formatter, matching SDK behavior.
    cancel_result = await tool_error_with_details(ctx, MCPToolCancellationError("cancelled"))
    assert cancel_result == "An error occurred while running the tool. Please try again. Error: cancelled"

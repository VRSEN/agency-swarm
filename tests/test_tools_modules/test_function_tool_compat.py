from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agents import FunctionTool, RunContextWrapper, function_tool as sdk_function_tool, tool_namespace
from agents.tool_context import ToolContext

from agency_swarm import Agent, function_tool


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

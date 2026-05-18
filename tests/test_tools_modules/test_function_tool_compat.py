from types import SimpleNamespace

import pytest
from agents import RunContextWrapper, function_tool
from agents.items import ToolApprovalItem
from agents.tool_context import ToolContext

from agency_swarm import Agent


@pytest.mark.asyncio
async def test_normalized_sdk_function_tool_preserves_manual_run_context_wrapper_state() -> None:
    """Manual RunContextWrapper calls should keep run state when converted to ToolContext."""
    seen_contexts: list[ToolContext[dict]] = []

    @function_tool
    async def inspect_context(ctx: RunContextWrapper[dict]) -> str:
        seen_contexts.append(ctx)
        return "ok"

    wrapper = RunContextWrapper(context={"value": 1})
    wrapper.turn_input.append({"role": "user", "content": "hello"})
    wrapper.tool_input = {"structured": True}
    approval_item = ToolApprovalItem(
        agent=SimpleNamespace(name="Agent"),
        raw_item={"type": "function_call", "call_id": "call_123", "name": "inspect_context"},
        tool_name="inspect_context",
    )
    wrapper.approve_tool(approval_item)

    agent = Agent(name="test", instructions="test", tools=[inspect_context])

    result = await agent.tools[0].on_invoke_tool(wrapper, "{}")

    assert result == "ok"
    assert len(seen_contexts) == 1
    tool_context = seen_contexts[0]
    assert isinstance(tool_context, ToolContext)
    assert tool_context.context is wrapper.context
    assert tool_context.usage is wrapper.usage
    assert tool_context.turn_input == wrapper.turn_input
    assert tool_context.tool_input is wrapper.tool_input
    assert tool_context.is_tool_approved("inspect_context", "call_123") is True

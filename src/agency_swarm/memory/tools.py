from __future__ import annotations

import json
from typing import Any, cast

from agents import FunctionTool, RunContextWrapper

from agency_swarm.context import MasterContext

from .types import MemoryOperation, MemoryScope, MemoryType, MemoryWriteRequest


def build_search_memory_tool() -> FunctionTool:
    async def on_invoke_tool(wrapper: RunContextWrapper[MasterContext], arguments_json_string: str) -> str:
        args = json.loads(arguments_json_string)
        context = wrapper.context
        if context.memory_manager is None or context.memory_identity is None:
            return "Memory is not configured for this run."
        current_agent = context.agents.get(context.current_agent_name or "")
        results = await context.memory_manager.search_memory(
            query=args["query"],
            memory_identity=context.memory_identity,
            agent_name=context.current_agent_name or "unknown",
            agent_config=getattr(current_agent, "memory", None),
            scopes=tuple(MemoryScope(scope) for scope in args.get("scopes", [])) if args.get("scopes") else None,
            providers=args.get("providers"),
            limit=args.get("limit"),
        )
        if not results:
            return "No memory results found."
        lines = [f"- [{item.provider_name}/{item.scope.value}] {item.content}" for item in results]
        return "\n".join(lines)

    return FunctionTool(
        name="search_memory",
        description="Search durable memory across configured memory providers.",
        params_json_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The memory query to search for."},
                "scopes": {
                    "type": "array",
                    "items": {"type": "string", "enum": [scope.value for scope in MemoryScope]},
                },
                "providers": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        on_invoke_tool=on_invoke_tool,
    )


def build_request_memory_write_tool() -> FunctionTool:
    async def on_invoke_tool(wrapper: RunContextWrapper[MasterContext], arguments_json_string: str) -> str:
        args = json.loads(arguments_json_string)
        context = wrapper.context
        if context.memory_manager is None or context.memory_identity is None:
            return "Memory is not configured for this run."
        if not context.current_agent_name:
            return "Current agent name is required for memory writes."
        current_agent = context.agents.get(context.current_agent_name)
        history = []
        if context.thread_manager is not None:
            try:
                history = context.thread_manager.get_conversation_history(
                    context.current_agent_name,
                    context.current_sender_name,
                )
            except Exception:
                history = []
        request = MemoryWriteRequest(
            operation=MemoryOperation(args["operation"]),
            content=args["content"],
            rationale=args["rationale"],
            scope=MemoryScope(args["scope"]),
            memory_type=MemoryType(args["memory_type"]),
            source_agent=context.current_agent_name,
            memory_identity=context.memory_identity,
            context_snapshot=cast(
                list[dict[str, Any]],
                history[-context.memory_manager.config.recent_message_limit :],
            ),
            requested_providers=args.get("providers"),
            record_id=args.get("record_id"),
            title=args.get("title"),
        )
        decision = await context.memory_manager.request_write(
            request=request,
            runtime_context=context,
            agent_config=getattr(current_agent, "memory", None),
        )
        if decision.mode.value == "allow":
            return "Memory write request queued."
        if decision.mode.value == "require_approval":
            return "Memory write requires approval."
        return "Memory write denied by policy."

    return FunctionTool(
        name="request_memory_write",
        description="Queue a durable memory write using the configured memory policy and providers.",
        params_json_schema={
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": [operation.value for operation in MemoryOperation]},
                "content": {"type": "string"},
                "rationale": {"type": "string"},
                "scope": {"type": "string", "enum": [scope.value for scope in MemoryScope]},
                "memory_type": {"type": "string", "enum": [memory_type.value for memory_type in MemoryType]},
                "providers": {"type": "array", "items": {"type": "string"}},
                "record_id": {"type": "string"},
                "title": {"type": "string"},
            },
            "required": ["operation", "content", "rationale", "scope", "memory_type"],
            "additionalProperties": False,
        },
        on_invoke_tool=on_invoke_tool,
    )

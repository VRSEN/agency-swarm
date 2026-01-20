from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from agents import TResponseInputItem
from agents.agent_output import AgentOutputSchema, AgentOutputSchemaBase
from agents.handoffs import Handoff as AgentsHandoff
from agents.items import HandoffOutputItem, MessageOutputItem, ReasoningItem, ToolCallItem, ToolCallOutputItem
from agents.tool import (
    ApplyPatchTool,
    CodeInterpreterTool,
    ComputerTool,
    FileSearchTool,
    FunctionTool,
    HostedMCPTool,
    ImageGenerationTool,
    LocalShellTool,
    ShellTool,
    WebSearchTool,
)
from openai.types.responses import ResponseOutputMessage, ResponseOutputText
from openai.types.responses.response_reasoning_item import ResponseReasoningItem

from agency_swarm.messages import MessageFilter
from agency_swarm.utils.files import get_chats_dir
from agency_swarm.utils.model_utils import get_model_name

if TYPE_CHECKING:
    from agency_swarm.agent.context_types import AgentRuntimeState
    from agency_swarm.agent.core import Agent

_CACHE_DIR_NAME = "starter_cache"
_SENSITIVE_KEYS = ("key", "secret", "token", "authorization", "password")


@dataclass(frozen=True)
class CachedStarter:
    prompt: str
    items: list[TResponseInputItem]
    metadata: dict[str, Any]


def normalize_starter_text(text: str) -> str:
    return text.strip().casefold()


def compute_starter_cache_fingerprint(agent: Agent, runtime_state: AgentRuntimeState | None = None) -> str:
    model_name = get_model_name(agent.model)
    tools = [_tool_signature(tool) for tool in agent.tools]
    runtime_tools = _runtime_tool_signatures(runtime_state)
    if runtime_tools:
        tools.extend(runtime_tools)
    handoffs = _handoff_signatures(agent, runtime_state)
    mcp_servers = [{"type": type(server).__name__, "name": server.name} for server in (agent.mcp_servers or [])]
    mcp_config = agent.mcp_config
    if isinstance(mcp_config, dict):
        sanitized_mcp_config = _sanitize_mapping(cast(dict[str, Any], mcp_config))
    else:
        sanitized_mcp_config = _serialize_value(mcp_config)
    payload = {
        "instructions": _instructions_signature(agent.instructions),
        "prompt": _serialize_value(agent.prompt),
        "model": model_name,
        "model_settings": _serialize_value(agent.model_settings),
        "input_guardrails": _serialize_value(agent.input_guardrails),
        "output_guardrails": _serialize_value(agent.output_guardrails),
        "tools": tools,
        "tool_use_behavior": _serialize_value(agent.tool_use_behavior),
        "reset_tool_choice": agent.reset_tool_choice,
        "mcp_servers": mcp_servers,
        "mcp_config": sanitized_mcp_config,
        "handoffs": handoffs,
        "output_type": _output_type_signature(agent.output_type),
    }
    digest = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return _hash_string(digest)


def extract_text_from_content(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            text_value = part.get("text")
            if isinstance(text_value, str):
                parts.append(text_value)
        if parts:
            return "".join(parts)
    return None


def extract_user_text(items: list[TResponseInputItem]) -> str | None:
    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        if item.get("role") != "user":
            continue
        text = extract_text_from_content(item.get("content"))
        if isinstance(text, str):
            return text
    return None


def is_simple_text_message(items: list[TResponseInputItem]) -> bool:
    user_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            return False
        if item.get("role") != "user":
            return False
        if item.get("callerAgent") is not None:
            return False
        user_items.append(cast(dict[str, Any], item))

    if len(user_items) != 1:
        return False

    content = user_items[0].get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                return False
            if part.get("type") != "input_text":
                return False
        return True
    return False


def match_conversation_starter(
    items: list[TResponseInputItem],
    starters: list[str] | None,
) -> str | None:
    if not starters:
        return None
    user_text = extract_user_text(items)
    if not user_text:
        return None
    normalized_message = normalize_starter_text(user_text)
    if not normalized_message:
        return None
    for starter in starters:
        if normalized_message == normalize_starter_text(starter):
            return starter
    return None


def extract_starter_segment(items: list[TResponseInputItem], starter: str) -> list[TResponseInputItem] | None:
    normalized_starter = normalize_starter_text(starter)
    if not normalized_starter:
        return None
    start_index: int | None = None
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if item.get("role") != "user":
            continue
        if item.get("callerAgent") is not None:
            continue
        text = extract_text_from_content(item.get("content"))
        if isinstance(text, str) and normalize_starter_text(text) == normalized_starter:
            start_index = idx
            break
    if start_index is None:
        return None
    end_index = len(items)
    for idx in range(start_index + 1, len(items)):
        item = items[idx]
        if not isinstance(item, dict):
            continue
        if item.get("role") == "user":
            if item.get("callerAgent") is not None:
                continue
            end_index = idx
            break
    segment = [item for item in items[start_index:end_index] if isinstance(item, dict)]
    return segment or None


def reorder_cached_items_for_tools(
    items: list[TResponseInputItem], primary_agent_name: str
) -> list[TResponseInputItem]:
    if not items:
        return items
    child_items_by_parent: dict[str, list[TResponseInputItem]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        parent_run_id = item.get("parent_run_id")
        if not isinstance(parent_run_id, str):
            continue
        child_items_by_parent.setdefault(parent_run_id, []).append(item)

    parents_with_tool_call: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("agent") != primary_agent_name:
            continue
        if item.get("type") not in MessageFilter.CALL_ID_CALL_TYPES:
            continue
        call_id = item.get("call_id")
        if isinstance(call_id, str):
            parents_with_tool_call.add(call_id)
        agent_run_id = item.get("agent_run_id")
        if isinstance(agent_run_id, str):
            parents_with_tool_call.add(agent_run_id)

    inserted_ids: set[int] = set()
    ordered: list[TResponseInputItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        parent_run_id = item.get("parent_run_id")
        if isinstance(parent_run_id, str) and parent_run_id in parents_with_tool_call:
            if id(item) not in inserted_ids:
                continue
        if id(item) in inserted_ids:
            continue
        ordered.append(item)
        inserted_ids.add(id(item))
        if item.get("agent") == primary_agent_name and item.get("type") in MessageFilter.CALL_ID_CALL_TYPES:
            insertion_keys: list[str] = []
            call_id = item.get("call_id")
            if isinstance(call_id, str):
                insertion_keys.append(call_id)
            agent_run_id = item.get("agent_run_id")
            if isinstance(agent_run_id, str) and agent_run_id not in insertion_keys:
                insertion_keys.append(agent_run_id)
            for key in insertion_keys:
                for child in child_items_by_parent.get(key, []):
                    if id(child) in inserted_ids:
                        continue
                    ordered.append(child)
                    inserted_ids.add(id(child))

    for children in child_items_by_parent.values():
        for child in children:
            if id(child) in inserted_ids:
                continue
            ordered.append(child)
            inserted_ids.add(id(child))
    return ordered


def load_cached_starter(
    agent_name: str,
    starter: str,
    *,
    expected_fingerprint: str | None = None,
) -> CachedStarter | None:
    path = _cache_path(agent_name, starter)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    items = payload.get("items")
    if not isinstance(items, list):
        return None
    raw_metadata = payload.get("metadata")
    if isinstance(raw_metadata, dict):
        metadata = cast(dict[str, Any], raw_metadata)
    else:
        metadata = {}
    prompt = payload.get("prompt")
    if not isinstance(prompt, str):
        prompt = starter
    if metadata.get("source") == "chat_history":
        return None
    if expected_fingerprint and metadata.get("fingerprint") != expected_fingerprint:
        return None
    if not extract_final_output_text(items):
        return None
    return CachedStarter(prompt=prompt, items=items, metadata=metadata)


def save_cached_starter(
    agent_name: str,
    starter: str,
    items: list[TResponseInputItem],
    metadata: dict[str, Any] | None = None,
    *,
    fingerprint: str | None = None,
) -> CachedStarter:
    resolved_metadata = dict(metadata or {})
    if fingerprint:
        resolved_metadata["fingerprint"] = fingerprint
    payload = {
        "prompt": starter,
        "agent": agent_name,
        "items": items,
        "metadata": resolved_metadata,
    }
    path = _cache_path(agent_name, starter)
    path.write_text(json.dumps(payload, indent=2))
    return CachedStarter(prompt=starter, items=items, metadata=resolved_metadata)


def load_cached_starters(
    agent_name: str,
    starters: list[str],
    *,
    expected_fingerprint: str | None = None,
) -> dict[str, CachedStarter]:
    cached: dict[str, CachedStarter] = {}
    for starter in starters:
        normalized = normalize_starter_text(starter)
        if not normalized:
            continue
        existing = load_cached_starter(agent_name, starter, expected_fingerprint=expected_fingerprint)
        if existing:
            cached[normalized] = existing
    return cached


def prepare_cached_items_for_replay(
    items: list[TResponseInputItem],
    *,
    run_trace_id: str,
    parent_run_id: str | None,
) -> list[TResponseInputItem]:
    now_us = int(time.time() * 1_000_000)
    agent_run_ids: dict[str, str] = {}
    call_id_map: dict[str | None, str] = {}
    replay_items: list[TResponseInputItem] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        copied = dict(item)
        agent_name = copied.get("agent")
        if not isinstance(agent_name, str) or not agent_name:
            agent_name = "Agent"
            copied["agent"] = agent_name
        run_id = agent_run_ids.setdefault(agent_name, f"agent_run_{uuid.uuid4().hex}")
        copied["agent_run_id"] = run_id
        copied["run_trace_id"] = run_trace_id
        if parent_run_id is not None:
            copied["parent_run_id"] = parent_run_id
        copied["timestamp"] = now_us + idx

        msg_type = copied.get("type")
        if msg_type in MessageFilter.CALL_ID_CALL_TYPES:
            old_call_id = copied.get("call_id")
            if not isinstance(old_call_id, str):
                old_call_id = None
            new_call_id = call_id_map.get(old_call_id)
            if new_call_id is None:
                new_call_id = f"call_{uuid.uuid4().hex}"
                call_id_map[old_call_id] = new_call_id
            copied["call_id"] = new_call_id
            copied["id"] = f"fc_{uuid.uuid4().hex}"
        elif msg_type in MessageFilter.CALL_ID_OUTPUT_TYPES:
            old_call_id = copied.get("call_id")
            if not isinstance(old_call_id, str):
                old_call_id = None
            new_call_id = call_id_map.get(old_call_id)
            if new_call_id is None:
                new_call_id = f"call_{uuid.uuid4().hex}"
                call_id_map[old_call_id] = new_call_id
            copied["call_id"] = new_call_id
            copied.pop("id", None)
        elif msg_type == "message" and copied.get("role") == "assistant":
            copied["id"] = f"msg_{uuid.uuid4().hex}"

        replay_items.append(cast(TResponseInputItem, copied))
    return replay_items


def filter_replay_items(items: list[TResponseInputItem]) -> list[TResponseInputItem]:
    filtered = [item for item in items if isinstance(item, dict) and item.get("role") != "user"]
    filtered = MessageFilter.filter_messages(filtered)
    filtered = MessageFilter.remove_orphaned_messages(filtered)
    return filtered


def extract_final_output_text(items: list[TResponseInputItem]) -> str:
    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        if item.get("role") != "assistant" or item.get("type") != "message":
            continue
        text = extract_text_from_content(item.get("content"))
        if isinstance(text, str):
            return text
    return ""


def parse_cached_output(response_text: str, output_type: type[Any] | AgentOutputSchemaBase | None) -> Any:
    if output_type is None or output_type is str:
        return response_text
    if isinstance(output_type, AgentOutputSchemaBase):
        output_schema = output_type
    else:
        output_schema = AgentOutputSchema(output_type)
    if output_schema.is_plain_text():
        return response_text
    return output_schema.validate_json(response_text)


def build_run_items_from_cached(agent: Any, items: list[TResponseInputItem]) -> list[Any]:
    run_items: list[Any] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_dict = cast(dict[str, Any], item)
        msg_type = item_dict.get("type")
        role = item_dict.get("role")
        if msg_type == "message" and role == "assistant":
            raw_id = item_dict.get("id")
            message_id = raw_id if isinstance(raw_id, str) else f"msg_{uuid.uuid4().hex}"
            text = extract_text_from_content(item_dict.get("content")) or ""
            output_message = ResponseOutputMessage(
                id=message_id,
                content=[ResponseOutputText(text=text, type="output_text", annotations=[], logprobs=[])],
                role="assistant",
                status="completed",
                type="message",
            )
            run_items.append(MessageOutputItem(raw_item=output_message, type="message_output_item", agent=agent))
            continue
        if msg_type in MessageFilter.CALL_ID_CALL_TYPES:
            run_items.append(ToolCallItem(raw_item=item_dict, agent=agent))
            continue
        if msg_type == "handoff_output_item":
            run_items.append(
                HandoffOutputItem(
                    agent=agent,
                    raw_item=cast(TResponseInputItem, item_dict),
                    source_agent=agent,
                    target_agent=agent,
                )
            )
            continue
        if msg_type in MessageFilter.CALL_ID_OUTPUT_TYPES:
            output_value = item_dict.get("output")
            run_items.append(ToolCallOutputItem(raw_item=item_dict, output=output_value, agent=agent))
            continue
        if msg_type == "reasoning":
            try:
                raw_reasoning = ResponseReasoningItem.model_validate(item_dict)
            except Exception:
                continue
            run_items.append(ReasoningItem(raw_item=raw_reasoning, agent=agent))
    return run_items


def _signature_sort_key(signature: dict[str, Any]) -> str:
    return json.dumps(signature, sort_keys=True, separators=(",", ":"))


def _unique_sorted_signatures(signatures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for signature in signatures:
        key = _signature_sort_key(signature)
        if key in seen:
            continue
        seen.add(key)
        unique.append(signature)
    return sorted(unique, key=_signature_sort_key)


def _runtime_tool_signatures(runtime_state: AgentRuntimeState | None) -> list[dict[str, Any]]:
    if runtime_state is None:
        return []
    signatures = [_tool_signature(tool) for tool in runtime_state.send_message_tools.values()]
    return _unique_sorted_signatures(signatures)


def _handoff_signature(handoff: AgentsHandoff) -> dict[str, Any]:
    schema = handoff.input_json_schema
    serialized_schema = _sanitize_mapping(schema) if isinstance(schema, dict) else _serialize_value(schema)
    return {
        "tool_name": handoff.tool_name,
        "agent_name": handoff.agent_name,
        "input_json_schema": serialized_schema,
    }


def _handoff_signatures(agent: Agent, runtime_state: AgentRuntimeState | None) -> list[dict[str, Any]]:
    handoffs = [handoff for handoff in agent.handoffs if isinstance(handoff, AgentsHandoff)]
    if runtime_state is not None:
        handoffs.extend([handoff for handoff in runtime_state.handoffs if isinstance(handoff, AgentsHandoff)])
    signatures = [_handoff_signature(handoff) for handoff in handoffs]
    return _unique_sorted_signatures(signatures)


def _hash_string(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _callable_signature(value: Any) -> dict[str, Any]:
    module = value.__module__
    try:
        qualname = value.__qualname__
    except AttributeError:
        qualname = value.__name__
    source_hash = None
    try:
        source_hash = _hash_string(inspect.getsource(value))
    except Exception:
        source_hash = None
    return {
        "module": module,
        "qualname": qualname,
        "source_hash": source_hash,
    }


def _serialize_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_value(val) for key, val in value.items()}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        data = dataclasses.asdict(cast(Any, value))
        return {key: _serialize_value(val) for key, val in data.items()}
    if callable(value):
        return _callable_signature(value)
    return type(value).__name__


def _sanitize_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in mapping.items():
        if any(token in key.lower() for token in _SENSITIVE_KEYS):
            continue
        sanitized[key] = _serialize_value(value)
    return sanitized


def _instructions_signature(instructions: Any) -> dict[str, Any]:
    if isinstance(instructions, str):
        return {"type": "text", "value": instructions}
    if callable(instructions):
        return {"type": "callable", "value": _callable_signature(instructions)}
    return {"type": type(instructions).__name__}


def _output_type_signature(output_type: Any) -> dict[str, Any] | None:
    if output_type is None:
        return None
    if isinstance(output_type, AgentOutputSchemaBase):
        return {"module": type(output_type).__module__, "name": output_type.name()}
    return {"module": output_type.__module__, "name": output_type.__name__}


def _serialize_tool_config(tool_config: Any) -> Any:
    serialized = _serialize_value(tool_config)
    if isinstance(serialized, dict):
        return _sanitize_mapping(serialized)
    return serialized


def _tool_signature(tool: Any) -> dict[str, Any]:
    signature: dict[str, Any] = {"type": type(tool).__name__}
    if isinstance(tool, FunctionTool):
        signature["name"] = tool.name
        signature["description"] = tool.description
        signature["params_json_schema"] = _sanitize_mapping(tool.params_json_schema)
        signature["strict_json_schema"] = tool.strict_json_schema
        return signature
    if isinstance(tool, FileSearchTool):
        signature["name"] = tool.name
        signature["vector_store_ids"] = _serialize_value(tool.vector_store_ids)
        signature["max_num_results"] = _serialize_value(tool.max_num_results)
        signature["include_search_results"] = _serialize_value(tool.include_search_results)
        signature["filters"] = _serialize_value(tool.filters)
        signature["ranking_options"] = _serialize_value(tool.ranking_options)
        return signature
    if isinstance(tool, WebSearchTool):
        signature["name"] = tool.name
        signature["user_location"] = _serialize_value(tool.user_location)
        signature["filters"] = _serialize_value(tool.filters)
        signature["search_context_size"] = _serialize_value(tool.search_context_size)
        return signature
    if isinstance(tool, HostedMCPTool):
        signature["name"] = tool.name
        signature["tool_config"] = _serialize_tool_config(tool.tool_config)
        return signature
    if isinstance(tool, CodeInterpreterTool):
        signature["name"] = tool.name
        signature["tool_config"] = _serialize_tool_config(tool.tool_config)
        return signature
    if isinstance(tool, ImageGenerationTool):
        signature["name"] = tool.name
        signature["tool_config"] = _serialize_tool_config(tool.tool_config)
        return signature
    if isinstance(tool, ComputerTool):
        signature["name"] = tool.name
        signature["computer"] = _serialize_value(tool.computer)
        return signature
    if isinstance(tool, ShellTool):
        signature["name"] = tool.name
        signature["executor"] = _serialize_value(tool.executor)
        return signature
    if isinstance(tool, LocalShellTool):
        signature["name"] = tool.name
        signature["executor"] = _serialize_value(tool.executor)
        return signature
    if isinstance(tool, ApplyPatchTool):
        signature["name"] = tool.name
        signature["editor"] = _serialize_value(tool.editor)
        return signature
    signature["name"] = type(tool).__name__
    return signature


def _get_cache_dir() -> Path:
    path = get_chats_dir() / _CACHE_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_agent_name(agent_name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", agent_name.strip())
    return cleaned or "agent"


def _cache_filename(agent_name: str, starter: str) -> str:
    normalized = normalize_starter_text(starter)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"{_safe_agent_name(agent_name)}_{digest}.json"


def _cache_path(agent_name: str, starter: str) -> Path:
    return _get_cache_dir() / _cache_filename(agent_name, starter)

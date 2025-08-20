"""
Message handling utilities for agents.

This module contains functions for processing, sanitizing, and validating
messages in agent conversations.
"""

import time
from typing import Any

from openai._utils._logs import logger


def sanitize_tool_calls_in_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Ensures only the most recent assistant message in the history has a 'tool_calls' field.
    Removes 'tool_calls' from all other messages.
    """
    # Find the index of the last assistant message
    last_assistant_idx = None
    for i in reversed(range(len(history))):
        if history[i].get("role") == "assistant":
            last_assistant_idx = i
            break
    if last_assistant_idx is None:
        return history
    # Remove 'tool_calls' from all assistant messages except the last one
    sanitized = []
    for idx, msg in enumerate(history):
        if msg.get("role") == "assistant" and "tool_calls" in msg and idx != last_assistant_idx:
            msg = dict(msg)
            msg.pop("tool_calls", None)
        sanitized.append(msg)
    return sanitized


def ensure_tool_calls_content_safety(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Ensures that assistant messages with tool_calls have non-null content.
    This prevents OpenAI API errors when switching between sync and streaming modes.
    """
    sanitized = []
    for msg in history:
        if msg.get("role") == "assistant" and msg.get("tool_calls") and msg.get("content") is None:
            # Create a copy to avoid modifying the original
            msg = dict(msg)
            # Generate descriptive content for tool calls
            tool_descriptions = []
            for tc in msg["tool_calls"]:
                if isinstance(tc, dict):
                    func_name = tc.get("function", {}).get("name", "unknown")
                    tool_descriptions.append(func_name)

            if tool_descriptions:
                msg["content"] = f"Using tools: {', '.join(tool_descriptions)}"
            else:
                msg["content"] = "Executing tool calls"

            logger.debug(f"Fixed null content for assistant message with tool calls: {msg.get('content')}")

        sanitized.append(msg)
    return sanitized


def resolve_token_settings(model_settings_dict: dict[str, Any], agent_name: str = "unknown") -> None:
    """
    Resolves conflicts between max_tokens, max_prompt_tokens, and max_completion_tokens.

    Args:
        model_settings_dict: Dictionary of model settings to modify in place
        agent_name: Name of the agent for logging purposes
    """
    has_max_tokens = "max_tokens" in model_settings_dict
    has_max_prompt_tokens = "max_prompt_tokens" in model_settings_dict
    has_max_completion_tokens = "max_completion_tokens" in model_settings_dict

    # Since oai only kept 1 parameter to manage tokens, write one of the existing parameters to max_tokens
    if has_max_tokens:
        # If max_tokens is specified, drop prompt and completion tokens
        if has_max_prompt_tokens or has_max_completion_tokens:
            logger.info(
                f"max_tokens is specified, ignoring max_prompt_tokens and max_completion_tokens "
                f"for agent '{agent_name}'"
            )
            model_settings_dict.pop("max_prompt_tokens", None)
            model_settings_dict.pop("max_completion_tokens", None)
    else:
        # If max_tokens is not specified, handle prompt/completion tokens
        if has_max_prompt_tokens and has_max_completion_tokens:
            # Both are present, prefer completion tokens and warn
            model_settings_dict["max_tokens"] = model_settings_dict["max_completion_tokens"]
            model_settings_dict.pop("max_prompt_tokens", None)
            model_settings_dict.pop("max_completion_tokens", None)
            logger.warning(
                f"Both max_prompt_tokens and max_completion_tokens specified for agent '{agent_name}'. "
                f"Using max_completion_tokens value ({model_settings_dict['max_tokens']}) "
                f"for max_tokens and ignoring max_prompt_tokens."
            )
        elif has_max_completion_tokens:
            # Only completion tokens present
            model_settings_dict["max_tokens"] = model_settings_dict["max_completion_tokens"]
            model_settings_dict.pop("max_completion_tokens", None)
        elif has_max_prompt_tokens:
            # Only prompt tokens present
            model_settings_dict["max_tokens"] = model_settings_dict["max_prompt_tokens"]
            model_settings_dict.pop("max_prompt_tokens", None)

    return model_settings_dict


def adjust_history_for_claude(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Anthropic/Claude requires each tool_use to be immediately followed by a tool_result
    in the next message. Due to unique approach to send_message tool, we need to adjust
    the history to ensure this requirement is met.
    """
    try:
        # Index existing outputs by call_id and store their original indices
        outputs_by_call_id: dict[str, dict[str, Any]] = {}
        for idx, msg in enumerate(history):
            if isinstance(msg, dict) and msg.get("type") == "function_call_output":
                cid = msg.get("call_id")
                if isinstance(cid, str) and cid:
                    outputs_by_call_id[cid] = {"item": msg, "idx": idx}

        adjusted: list[dict[str, Any]] = []
        consumed_call_ids: set[str] = set()

        i = 0
        n = len(history)
        while i < n:
            msg = history[i]

            # Skip original outputs that we will relocate next to their calls
            if (
                isinstance(msg, dict)
                and msg.get("type") == "function_call_output"
                and isinstance(msg.get("call_id"), str)
                and msg.get("call_id") in consumed_call_ids
            ):
                i += 1
                continue

            adjusted.append(msg)

            if isinstance(msg, dict) and msg.get("type") == "function_call" and msg.get("name") == "send_message":
                cid = msg.get("call_id")
                if isinstance(cid, str) and cid:
                    # If next item is already the correct output, do nothing
                    if i + 1 < n:
                        nxt = history[i + 1]
                        if (
                            isinstance(nxt, dict)
                            and nxt.get("type") == "function_call_output"
                            and nxt.get("call_id") == cid
                        ):
                            i += 1  # advance past the adjacent output we just acknowledged
                            adjusted.append(nxt)
                            continue
                    # Otherwise, move an existing matching output if present later
                    if cid in outputs_by_call_id:
                        adjusted.append(outputs_by_call_id[cid]["item"])
                        consumed_call_ids.add(cid)
                        # do not continue; allow loop increment below
                    else:
                        # Look ahead for the first assistant message with non-empty content
                        synthesized_output = None
                        for j in range(i + 1, n):
                            cand = history[j]
                            if isinstance(cand, dict) and cand.get("role") == "assistant":
                                content = cand.get("content")
                                if isinstance(content, str) and content.strip():
                                    synthesized_output = content
                                    break
                        if synthesized_output is not None:
                            synthesized_item: dict[str, Any] = {
                                "type": "function_call_output",
                                "call_id": cid,
                                "output": synthesized_output,
                                # Include agency metadata fields in-memory to mirror original snippet
                                # (they will be stripped before sending to the model)
                                "agent": msg.get("agent"),
                                "callerAgent": msg.get("callerAgent"),
                                "timestamp": int(time.time() * 1000),
                            }
                            if "agent_run_id" in msg:
                                synthesized_item["agent_run_id"] = msg.get("agent_run_id")
                            adjusted.append(synthesized_item)
            i += 1

        return adjusted
    except Exception:
        # On any unexpected error, return history unchanged
        return history

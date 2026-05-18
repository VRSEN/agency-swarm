from typing import Any

from agents import Agent as BaseAgent


def _iter_handoff_targets(agent: Any) -> tuple[Any, ...]:
    targets: list[Any] = []
    for handoff_item in getattr(agent, "handoffs", None) or ():
        if isinstance(handoff_item, BaseAgent):
            targets.append(handoff_item)
            continue
        agent_ref = getattr(handoff_item, "_agent_ref", None)
        target_agent = agent_ref() if agent_ref is not None else None
        if target_agent is not None:
            targets.append(target_agent)
    return tuple(targets)


def _iter_send_message_recipients(agent: Any, master_context: Any | None) -> tuple[Any, ...]:
    recipients: list[Any] = []
    for tool in getattr(agent, "tools", None) or ():
        tool_recipients = getattr(tool, "recipients", None)
        if isinstance(tool_recipients, dict):
            recipients.extend(tool_recipients.values())

    runtime_map = getattr(master_context, "agent_runtime_state", None)
    agent_name = getattr(agent, "name", None)
    runtime_state = (
        runtime_map.get(agent_name) if isinstance(runtime_map, dict) and isinstance(agent_name, str) else None
    )
    if runtime_state is None:
        return tuple(recipients)

    recipients.extend((getattr(runtime_state, "subagents", None) or {}).values())
    for tool in (getattr(runtime_state, "send_message_tools", None) or {}).values():
        tool_recipients = getattr(tool, "recipients", None)
        if isinstance(tool_recipients, dict):
            recipients.extend(tool_recipients.values())
    return tuple(recipients)


def collect_runner_compatible_agents(agent: Any, master_context: Any | None) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    locked_agents: list[Any] = []
    settings_agents: list[Any] = []
    seen_locked: set[int] = set()
    seen_settings: set[int] = set()
    expanded: set[tuple[int, bool]] = set()
    stack = [(agent, True)]
    while stack:
        current_agent, settings_scope = stack.pop()
        agent_id = id(current_agent)
        if agent_id not in seen_locked:
            seen_locked.add(agent_id)
            locked_agents.append(current_agent)
        if settings_scope and agent_id not in seen_settings:
            seen_settings.add(agent_id)
            settings_agents.append(current_agent)

        expand_key = (agent_id, settings_scope)
        if expand_key in expanded:
            continue
        expanded.add(expand_key)

        stack.extend((target_agent, settings_scope) for target_agent in _iter_handoff_targets(current_agent))
        stack.extend(
            (recipient_agent, False) for recipient_agent in _iter_send_message_recipients(current_agent, master_context)
        )

    return tuple(locked_agents), tuple(settings_agents)

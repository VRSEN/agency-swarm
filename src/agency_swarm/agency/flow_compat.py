"""Compatibility helpers for agency flow parsing."""

from typing import cast

from agency_swarm.agent.agent_flow import AgentFlow
from agency_swarm.agent.core import Agent

CommunicationFlowEntry = (
    tuple[Agent, Agent]  # Basic (sender, receiver) pair
    | tuple[AgentFlow, type]  # Agent flow with tool class
    | tuple[Agent, Agent, type]  # Individual (sender, receiver, tool_class)
    | tuple[Agent, Agent, list[type] | tuple[type, ...]]  # Individual pair with multiple tool classes
    | AgentFlow  # Standalone agent flow (uses default tool)
)

ParseAgentFlowsResult = tuple[
    list[tuple[Agent, Agent]],
    dict[tuple[str, str], list[type]],
    set[tuple[str, str]],
]


def normalize_parse_agent_flows_result(result: object) -> ParseAgentFlowsResult:
    """Accept legacy local patches that still return the old two-value shape."""
    if not isinstance(result, tuple):
        raise TypeError("parse_agent_flows must return a tuple.")

    if len(result) == 3:
        flows, mapping, defaults = result
        return (
            cast(list[tuple[Agent, Agent]], flows),
            cast(dict[tuple[str, str], list[type]], mapping),
            cast(set[tuple[str, str]], defaults),
        )

    if len(result) == 2:
        flows, raw_mapping = result
        normalized: dict[tuple[str, str], list[type]] = {}
        legacy_mapping = cast(
            dict[tuple[str, str], type | list[type] | tuple[type, ...]],
            raw_mapping,
        )
        for pair, tool_classes in legacy_mapping.items():
            normalized[pair] = list(tool_classes) if isinstance(tool_classes, (list, tuple)) else [tool_classes]
        return cast(list[tuple[Agent, Agent]], flows), normalized, set()

    raise ValueError("parse_agent_flows must return 2 or 3 values.")

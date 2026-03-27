from __future__ import annotations

import operator

import pytest

from agency_swarm import Agent
from agency_swarm.agent.agent_flow import AgentFlow


def _agent(name: str) -> Agent:
    return Agent(name=name, instructions=f"Instructions for {name}", model="gpt-5.4-mini")


def test_agent_flow_gt_rejects_non_agent() -> None:
    flow = AgentFlow([_agent("A"), _agent("B")])
    with pytest.raises(TypeError, match="Can only chain to Agent instances"):
        operator.gt(flow, object())


def test_agent_flow_lt_rejects_non_agent() -> None:
    flow = AgentFlow([_agent("A"), _agent("B")])
    with pytest.raises(TypeError, match="Can only chain to Agent instances"):
        operator.lt(flow, object())


def test_agent_flow_chain_and_repr() -> None:
    agent_a = _agent("A")
    agent_b = _agent("B")
    agent_c = _agent("C")
    agent_d = _agent("D")

    flow = AgentFlow([agent_a, agent_b])
    expanded = flow > agent_c
    prepended = expanded < agent_d

    assert expanded.get_all_flows() == [(agent_a, agent_b), (agent_b, agent_c)]
    assert prepended.get_all_flows() == [(agent_d, agent_a), (agent_a, agent_b), (agent_b, agent_c)]
    assert repr(expanded) == "AgentFlow(A > B > C)"


def test_agent_flow_bool_tracks_and_clears_chain_flows() -> None:
    AgentFlow.get_and_clear_chain_flows()
    agent_a = _agent("A")
    agent_b = _agent("B")
    agent_c = _agent("C")

    flow = AgentFlow([agent_a, agent_b, agent_c])

    assert bool(flow) is True
    assert bool(flow) is True  # duplicate truthiness should not duplicate tracked flows

    tracked = AgentFlow.get_and_clear_chain_flows()
    assert tracked == [(agent_a, agent_b), (agent_b, agent_c)]
    assert AgentFlow.get_and_clear_chain_flows() == []

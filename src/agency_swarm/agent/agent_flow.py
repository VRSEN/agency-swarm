"""
Agent flow management for communication chains.

This module provides the AgentFlow class for creating and managing
agent communication chains using the > and < operators.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent


class AgentFlow:
    """
    Represents a flow of agents created with the > or < operators for communication flows.

    This class allows building flows like: agent1 > agent2 > agent3 > agent4 > ...
    Stores the complete chain for proper expansion in Agency parsing.
    """

    # Class variable to track flows during chain evaluation
    _chain_flows: list[tuple["Agent", "Agent"]] = []

    def __init__(self, agents: list["Agent"], _all_flows: list[tuple["Agent", "Agent"]] | None = None):
        self.agents = agents
        # Store all individual flows that should be created from this chain
        self._all_flows = _all_flows or []

        # If we have a simple sequence, add the sequential flows
        if not self._all_flows and len(agents) >= 2:
            for i in range(len(agents) - 1):
                self._all_flows.append((agents[i], agents[i + 1]))

    def __gt__(self, other: "Agent") -> "AgentFlow":
        """Allow chaining with > operator: flow > agent"""
        # Import here to avoid circular import
        from agency_swarm.agent.core import Agent

        if not isinstance(other, Agent):
            raise TypeError("Can only chain to Agent instances")

        # Create new flow with additional agent and preserve all existing flows
        new_agents = self.agents + [other]
        new_all_flows = self._all_flows.copy()

        # Add the new flow from last agent to new agent
        new_all_flows.append((self.agents[-1], other))

        return AgentFlow(new_agents, new_all_flows)

    def __lt__(self, other: "Agent") -> "AgentFlow":
        """Allow chaining with < operator: flow < agent (prepends to chain)"""
        # Import here to avoid circular import
        from agency_swarm.agent.core import Agent

        if not isinstance(other, Agent):
            raise TypeError("Can only chain to Agent instances")

        # Create new flow with agent prepended and preserve all existing flows
        new_agents = [other] + self.agents
        new_all_flows = self._all_flows.copy()

        # Add the new flow from new agent to first existing agent
        new_all_flows.insert(0, (other, self.agents[0]))

        return AgentFlow(new_agents, new_all_flows)

    def get_all_flows(self) -> list[tuple["Agent", "Agent"]]:
        """Get all individual agent-to-agent flows represented by this chain."""
        return self._all_flows.copy()

    def __bool__(self) -> bool:
        """AgentFlow is always truthy, but this is called in comparison chains."""
        # Store this flow globally when it's being evaluated in a comparison chain
        # This is a hack to work around Python's comparison chaining

        # Add all flows from this AgentFlow to the global tracker
        for flow in self._all_flows:
            if flow not in AgentFlow._chain_flows:
                AgentFlow._chain_flows.append(flow)

        return True

    @classmethod
    def get_and_clear_chain_flows(cls) -> list[tuple["Agent", "Agent"]]:
        """Get all flows accumulated during chain evaluation and clear the tracker."""
        flows = cls._chain_flows.copy()
        cls._chain_flows.clear()
        return flows

    def __repr__(self) -> str:
        agent_names = [agent.name for agent in self.agents]
        return f"AgentFlow({' > '.join(agent_names)})"

import inspect
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

from agents import RunContextWrapper
from agents.handoffs import Handoff
from agents.realtime import RealtimeAgent as SDKRealtimeAgent, realtime_handoff

from agency_swarm.agent.context_types import AgentRuntimeState
from agency_swarm.agent.core import Agent
from agency_swarm.context import MasterContext
from agency_swarm.realtime.agent import RealtimeAgent

if TYPE_CHECKING:
    from agency_swarm.agency.core import Agency


class RealtimeAgency:
    """Realtime-aware facade built from an existing `Agency`.

    It converts each registered Agent into a distinct `RealtimeAgent`, enforces that
    every communication path is modeled as a handoff, and exposes the data needed to
    drive the realtime runner.
    """

    def __init__(self, source: "Agency", agent: Agent | None = None) -> None:
        self._source = source
        self._realtime_agents: dict[str, RealtimeAgent] = {
            name: RealtimeAgent(agent_instance) for name, agent_instance in source.agents.items()
        }
        self._entry_agent = self._resolve_entry(agent)
        self._populate_handoffs()

    @property
    def source(self) -> "Agency":
        return self._source

    @property
    def entry_agent(self) -> RealtimeAgent:
        return self._entry_agent

    @property
    def agents(self) -> dict[str, RealtimeAgent]:
        return self._realtime_agents

    @property
    def source_agents(self) -> dict[str, Agent]:
        return self._source.agents

    @property
    def shared_instructions(self) -> str | None:
        return self._source.shared_instructions or None

    @property
    def user_context(self) -> dict[str, Any]:
        return self._source.user_context

    @property
    def runtime_state_map(self) -> dict[str, AgentRuntimeState]:
        return self._source._agent_runtime_state

    def _resolve_entry(self, agent: Agent | None) -> RealtimeAgent:
        if agent is None:
            if not self._source.entry_points:
                raise ValueError("RealtimeAgency requires the source Agency to declare an entry point.")
            candidate = self._source.entry_points[0]
        else:
            if agent.name not in self._source.agents:
                raise ValueError(f"Agent '{agent.name}' is not registered in the source Agency.")
            candidate = agent

        realtime_agent = self._realtime_agents.get(candidate.name)
        if realtime_agent is None:
            raise ValueError(f"Realtime agent for '{candidate.name}' could not be constructed.")
        return realtime_agent

    def _populate_handoffs(self) -> None:
        runtime_state_map = self.runtime_state_map
        for agent_name, realtime_agent in self._realtime_agents.items():
            runtime_state = runtime_state_map.get(agent_name)
            if runtime_state is None:
                raise ValueError(f"No runtime state available for agent '{agent_name}'.")

            converted = self._convert_handoffs(
                source_agent=self._source.agents[agent_name],
                runtime_state=runtime_state,
                realtime_agent=realtime_agent,
            )
            realtime_agent.handoffs = cast(
                list[SDKRealtimeAgent[MasterContext] | Handoff[Any, SDKRealtimeAgent[Any]]],
                converted,
            )

    def _convert_handoffs(
        self,
        *,
        source_agent: Agent,
        runtime_state: AgentRuntimeState,
        realtime_agent: RealtimeAgent,
    ) -> list[Handoff[Any, SDKRealtimeAgent[MasterContext]]]:
        original_handoffs = getattr(runtime_state, "handoffs", [])
        if not original_handoffs:
            if getattr(runtime_state, "send_message_tools", {}):
                raise ValueError(
                    f"RealtimeAgency requires communication flows to be modeled with SendMessageHandoff. "
                    f"Agent '{source_agent.name}' has send_message tools but no handoffs."
                )
            return []

        converted: list[Handoff[Any, SDKRealtimeAgent[MasterContext]]] = []
        for original in original_handoffs:
            target = self._realtime_agents.get(original.agent_name)
            if target is None:
                raise ValueError(
                    f"Handoff '{original.tool_name}' on agent '{source_agent.name}' "
                    f"targets unknown agent '{original.agent_name}'."
                )

            realtime_handoff_obj = realtime_handoff(
                target,
                tool_name_override=original.tool_name,
                tool_description_override=original.tool_description,
                is_enabled=_wrap_is_enabled(original.is_enabled, source_agent),
            )

            original_on_invoke = original.on_invoke_handoff

            async def _on_invoke(
                ctx: RunContextWrapper[Any], input_json: str | None = None, *, _orig=original_on_invoke, _target=target
            ) -> SDKRealtimeAgent[MasterContext]:
                await _orig(ctx, input_json or "")
                return _target

            realtime_handoff_obj.on_invoke_handoff = _on_invoke
            realtime_handoff_obj.input_filter = original.input_filter
            realtime_handoff_obj.input_json_schema = original.input_json_schema
            realtime_handoff_obj.strict_json_schema = original.strict_json_schema
            converted.append(realtime_handoff_obj)
        return converted


def _wrap_is_enabled(
    is_enabled: bool | Callable[[RunContextWrapper[Any], Agent], Any],
    source_agent: Agent,
) -> bool | Callable[[RunContextWrapper[Any], SDKRealtimeAgent[MasterContext]], Awaitable[bool]]:
    if not callable(is_enabled):
        return bool(is_enabled)

    async def _wrapped(ctx: RunContextWrapper[Any], _: SDKRealtimeAgent[MasterContext]) -> bool:
        result = is_enabled(ctx, source_agent)
        if inspect.isawaitable(result):
            return bool(await cast(Awaitable[Any], result))
        return bool(result)

    return _wrapped

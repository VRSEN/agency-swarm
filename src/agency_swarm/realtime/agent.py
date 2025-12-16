import inspect
from collections.abc import Awaitable, Callable
from typing import Any, cast

from agents import RunContextWrapper
from agents.agent import MCPConfig
from agents.realtime import RealtimeAgent as SDKRealtimeAgent

from agency_swarm.agent.core import Agent
from agency_swarm.context import MasterContext


class RealtimeAgent(SDKRealtimeAgent[MasterContext]):
    """RealtimeAgent wrapper that preserves the interface of agency_swarm.agent.core.Agent."""

    def __init__(self, source: Agent) -> None:
        self._source = source
        instructions = _wrap_instructions(source)
        super().__init__(
            name=source.name,
            instructions=instructions,
            handoff_description=source.handoff_description,
            tools=list(source.tools),
            mcp_servers=list(source.mcp_servers),
            mcp_config=cast(MCPConfig, dict(source.mcp_config)),
            prompt=source.prompt if (source.prompt is None or not callable(source.prompt)) else None,
            output_guardrails=list(source.output_guardrails),
        )
        self.voice = source.voice

    @property
    def source(self) -> Agent:
        """Return the originating agency-swarm Agent."""
        return self._source


def _wrap_instructions(
    agent: Agent,
) -> str | Callable[[RunContextWrapper[Any], SDKRealtimeAgent[MasterContext]], Awaitable[str]] | None:
    instructions = agent.instructions
    if instructions is None or isinstance(instructions, str):
        return cast(str | None, instructions)

    typed = cast(Callable[[RunContextWrapper[Any], Agent], Awaitable[str] | str], instructions)

    async def _wrapped(ctx: RunContextWrapper[Any], _: SDKRealtimeAgent[MasterContext]) -> str:
        result = typed(ctx, agent)
        if inspect.isawaitable(result):
            return cast(str, await result)
        return cast(str, result)

    return _wrapped

from typing import Any

from agents import ModelSettings, RunConfig, RunHooks, RunResult, TResponseInputItem

from agency_swarm import Agent
from agency_swarm.agent.context_types import AgencyContext
from tests.deterministic_model import DeterministicModel


def _make_agent(name: str, response_text: str = "Test response") -> Agent:
    return Agent(
        name=name,
        instructions="You are a test agent.",
        model=DeterministicModel(default_response=response_text),
        model_settings=ModelSettings(temperature=0.0),
    )


class CapturingAgent(Agent):
    def __init__(self, name: str, response_text: str = "Test response") -> None:
        super().__init__(
            name=name,
            instructions="You are a test agent.",
            model=DeterministicModel(default_response=response_text),
            model_settings=ModelSettings(temperature=0.0),
        )
        self.last_context_override: dict[str, Any] | None = None
        self.last_hooks_override: RunHooks | None = None
        self.last_agency_context: AgencyContext | None = None
        self.last_message: str | list[TResponseInputItem] | None = None

    async def get_response(
        self,
        message: str | list[TResponseInputItem],
        sender_name: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        file_ids: list[str] | None = None,
        additional_instructions: str | None = None,
        agency_context: AgencyContext | None = None,
        **kwargs: Any,
    ) -> RunResult:
        self.last_message = message
        self.last_context_override = context_override
        self.last_hooks_override = hooks_override
        self.last_agency_context = agency_context
        return await super().get_response(
            message=message,
            sender_name=sender_name,
            context_override=context_override,
            hooks_override=hooks_override,
            run_config_override=run_config_override,
            file_ids=file_ids,
            additional_instructions=additional_instructions,
            agency_context=agency_context,
            **kwargs,
        )

    def get_response_stream(  # type: ignore[override]
        self,
        message: str | list[dict[str, Any]],
        sender_name: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        file_ids: list[str] | None = None,
        additional_instructions: str | None = None,
        agency_context: AgencyContext | None = None,
        parent_run_id: str | None = None,
        **kwargs: Any,
    ):
        self.last_message = message
        self.last_context_override = context_override
        self.last_hooks_override = hooks_override
        self.last_agency_context = agency_context
        return super().get_response_stream(
            message=message,
            sender_name=sender_name,
            context_override=context_override,
            hooks_override=hooks_override,
            run_config_override=run_config_override,
            file_ids=file_ids,
            additional_instructions=additional_instructions,
            agency_context=agency_context,
            parent_run_id=parent_run_id,
            **kwargs,
        )

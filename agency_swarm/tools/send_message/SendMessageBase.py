from abc import ABC
from typing import ClassVar, Union

from pydantic import Field, field_validator

from agency_swarm.agents.agent import Agent
from agency_swarm.threads.thread import Thread
from agency_swarm.threads.thread_async import ThreadAsync
from agency_swarm.tools import BaseTool


class SendMessageBase(BaseTool, ABC):
    recipient: str = Field(
        ...,
        description="Recipient agent that you want to send the message to. This field will be overriden inside the agency class.",
    )

    _agents_and_threads: ClassVar = None

    @field_validator("additional_instructions", mode="before", check_fields=False)
    @classmethod
    def validate_additional_instructions(cls, value):
        # previously the parameter was a list, now it's a string
        # add compatibility for old code
        if isinstance(value, list):
            return "\n".join(value)
        return value

    def _get_thread(self) -> Thread | ThreadAsync:
        strategy = self._caller_agent.agency.thread_strategy
        recipient_agent = self.get_agent_by_name(self.recipient.value)
        # strategy example:
        # {
        #     "always_new": [
        #         (some_agent_1, some_agent_2), # use instances for agents
        #         (Tool_1, some_agent_3) # use classes for tools
        #     ]
        # }
        if "always_new" in strategy and (
            (isinstance(self._caller_agent, BaseTool) and (type(self._caller_agent), recipient_agent) in strategy["always_new"]) or
            (isinstance(self._caller_agent, Agent) and (self._caller_agent, recipient_agent) in strategy["always_new"])
        ):
            return Thread(agent=self._caller_agent, recipient_agent=recipient_agent)
        # default: "always_same"
        return self._agents_and_threads[self._caller_agent.name][self.recipient.value]

    def _get_main_thread(self) -> Thread | ThreadAsync:
        return self._agents_and_threads["main_thread"]

    def _get_recipient_agent(self) -> Agent:
        return self._agents_and_threads[self._caller_agent.name][
            self.recipient.value
        ].recipient_agent

    def _get_completion(self, message: Union[str, None] = None, **kwargs):
        thread = self._get_thread()

        print(f"SendMessage: {message}")

        if self.ToolConfig.async_mode == "threading":
            return thread.get_completion_async(message=message, **kwargs)
        else:
            return thread.get_completion(
                message=message,
                event_handler=self._event_handler,
                yield_messages=not self._event_handler,
                **kwargs,
            )

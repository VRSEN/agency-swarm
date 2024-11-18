from agency_swarm.agents.agent import Agent
from agency_swarm.threads.thread import Thread
from typing import ClassVar, Union
from pydantic import Field, field_validator
from agency_swarm.threads.thread_async import ThreadAsync
from agency_swarm.tools import BaseTool
from abc import ABC

class SendMessageBase(BaseTool, ABC):
    recipient: str = Field(..., description="Recipient agent that you want to send the message to. This field will be overriden inside the agency class.")
    
    _agents_and_threads: ClassVar = None

    @field_validator('additional_instructions', mode='before', check_fields=False)
    @classmethod
    def validate_additional_instructions(cls, value):
        # previously the parameter was a list, now it's a string
        # add compatibility for old code
        if isinstance(value, list):
            return "\n".join(value)
        return value
        
    def _get_thread(self) -> Thread | ThreadAsync:
        return self._agents_and_threads[self._caller_agent.name][self.recipient.value]
    
    def _get_main_thread(self) -> Thread | ThreadAsync:
        return self._agents_and_threads["main_thread"]
    
    def _get_recipient_agent(self) -> Agent:
        return self._agents_and_threads[self._caller_agent.name][self.recipient.value].recipient_agent
    
    def _get_completion(self, message: Union[str, None] = None, **kwargs):
        thread = self._get_thread()

        if self.ToolConfig.async_mode == "threading":
            return thread.get_completion_async(message=message, **kwargs)
        else:
            return thread.get_completion(message=message, 
                                        event_handler=self._event_handler,
                                        yield_messages=not self._event_handler,
                                        **kwargs)
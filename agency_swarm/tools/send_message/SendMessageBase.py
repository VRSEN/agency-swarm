from agency_swarm.agents.agent import Agent
from agency_swarm.threads.thread import Thread
from typing import ClassVar
from pydantic import Field
from agency_swarm.threads.thread_async import ThreadAsync
from agency_swarm.tools import BaseTool
from abc import ABC

class SendMessageBase(BaseTool, ABC):
    """Use this tool to facilitate direct, synchronous communication between specialized agents within your agency. When you send a message using this tool, you receive a response exclusively from the designated recipient agent. To continue the dialogue, invoke this tool again with the desired recipient agent and your follow-up message. Remember, communication here is synchronous; the recipient agent won't perform any tasks post-response. You are responsible for relaying the recipient agent's responses back to the user, as the user does not have direct access to these replies. Keep engaging with the tool for continuous interaction until the task is fully resolved. Do not send more than 1 message at a time."""
    
    recipient: str = Field(..., description="Recipient agent that you want to send the message to. This field will be overriden inside the agency class.")
    _agents_and_threads: ClassVar = None

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.startswith("SendMessage"):
            raise TypeError(f"Class name '{cls.__name__}' must start with 'SendMessage'.")
        
    def _get_thread(self) -> Thread | ThreadAsync:
        return self._agents_and_threads[self._caller_agent.name][self.recipient.value]
    
    def _get_main_thread(self) -> Thread | ThreadAsync:
        return self._agents_and_threads["main_thread"]
    
    def _get_recipient_agent(self) -> Agent:
        return self._agents_and_threads[self._caller_agent.name][self.recipient.value].recipient_agent
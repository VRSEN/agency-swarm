from agency_swarm.threads.thread import Thread
from typing import ClassVar, Optional, List, Type
from pydantic import Field, field_validator, model_validator
from agency_swarm.tools import BaseTool
from abc import ABC

class SendMessageBase(BaseTool, ABC):
    """Use this tool to facilitate direct, synchronous communication between specialized agents within your agency. When you send a message using this tool, you receive a response exclusively from the designated recipient agent. To continue the dialogue, invoke this tool again with the desired recipient agent and your follow-up message. Remember, communication here is synchronous; the recipient agent won't perform any tasks post-response. You are responsible for relaying the recipient agent's responses back to the user, as the user does not have direct access to these replies. Keep engaging with the tool for continuous interaction until the task is fully resolved. Do not send more than 1 message at a time."""
    
    recipient: str = Field(..., description="Recipient agent that you want to send the message to. This field will be overriden inside the agency class.")
    
    _agents_and_threads: ClassVar = None
    _thread_type: ClassVar[Type[Thread]] = Thread # thread type assigned by the agency class

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.startswith("SendMessage"):
            raise TypeError(f"Class name '{cls.__name__}' must start with 'SendMessage'.")
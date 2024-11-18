from agency_swarm.threads.thread import Thread
from typing import ClassVar, Optional, List, Type
from pydantic import Field, field_validator, model_validator
from .SendMessageBase import SendMessageBase

class SendMessageQuick(SendMessageBase):
    """Use this tool to facilitate direct, synchronous communication between specialized agents within your agency. When you send a message using this tool, you receive a response exclusively from the designated recipient agent. To continue the dialogue, invoke this tool again with the desired recipient agent and your follow-up message. Remember, communication here is synchronous; the recipient agent won't perform any tasks post-response. You are responsible for relaying the recipient agent's responses back to the user, as the user does not have direct access to these replies. Keep engaging with the tool for continuous interaction until the task is fully resolved. Do not send more than 1 message to the same recipient agent at the same time."""
    message: str = Field(
        ..., 
        description="Specify the task required for the recipient agent to complete. Focus on clarifying what the task entails, rather than providing exact instructions. Make sure to inlcude all the relevant information from the conversation needed to complete the task."
    )
    
    def run(self):
        return self._get_completion(message=self.message)
from agency_swarm.threads.thread import Thread
from typing import ClassVar, Optional, List, Type
from pydantic import Field, field_validator, model_validator
from .SendMessageBase import SendMessageBase

class SendMessage(SendMessageBase):
    """Use this tool to facilitate direct, synchronous communication between specialized agents within your agency. When you send a message using this tool, you receive a response exclusively from the designated recipient agent. To continue the dialogue, invoke this tool again with the desired recipient agent and your follow-up message. Remember, communication here is synchronous; the recipient agent won't perform any tasks post-response. You are responsible for relaying the recipient agent's responses back to the user, as the user does not have direct access to these replies. Keep engaging with the tool for continuous interaction until the task is fully resolved. Do not send more than 1 message to the same recipient agent at the same time."""
    my_primary_instructions: str = Field(
        ..., 
        description=(
            "Please repeat your primary instructions step-by-step, including both completed "
            "and the following next steps that you need to perform. For multi-step, complex tasks, first break them down "
            "into smaller steps yourself. Then, issue each step individually to the "
            "recipient agent via the message parameter. Each identified step should be "
            "sent in a separate message. Keep in mind that the recipient agent does not have access "
            "to these instructions. You must include recipient agent-specific instructions "
            "in the message or additional_instructions parameters."
        )
    )
    message: str = Field(
        ..., 
        description="Specify the task required for the recipient agent to complete. Focus on clarifying what the task entails, rather than providing exact instructions. Make sure to inlcude all the relevant information needed to complete the task."
    )
    message_files: Optional[List[str]] = Field(
        default=None,
        description="A list of file IDs to be sent as attachments to this message. Only use this if you have the file ID that starts with 'file-'.",
        examples=["file-1234", "file-5678"]
    )
    additional_instructions: Optional[str] = Field(
        default=None,
        description="Additional context or instructions from the conversation needed by the recipient agent to complete the task."
    )


    @model_validator(mode='after')
    def validate_files(self):
        if hasattr(self, 'message') and "file-" in self.message or (self.additional_instructions and "file-" in self.additional_instructions):
            if not self.message_files:
                raise ValueError("You must include file IDs in message_files parameter.")
        return self

    @field_validator('additional_instructions', mode='before')
    @classmethod
    def validate_additional_instructions(cls, value):
        if isinstance(value, list):
            return "\n".join(value)
        return value

    
    def run(self):
        thread = self._get_thread()

        message = thread.get_completion(message=self.message,
                                message_files=self.message_files,
                                event_handler=self._event_handler,
                                yield_messages=not self._event_handler,
                                additional_instructions=self.additional_instructions,
                                )

        return message or ""
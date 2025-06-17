from typing import Any

from agents import TResponseInputItem
from pydantic import BaseModel, Field, field_validator


class AttachmentTool(BaseModel):
    type: str


class Attachment(BaseModel):
    file_id: str
    tools: list[AttachmentTool]


class ConversationThread(BaseModel):
    items: list[TResponseInputItem]
    metadata: dict[str, Any] = {}


class BaseRequest(BaseModel):
    message: str
    chat_history: dict[str, ConversationThread] = Field(
        None,
        description=(
            "Entire chat history containing previous messages across all threads. "
            "Should be provided in a form of {'thread_1': ConversationThread, 'thread_2': ConversationThread, ...}"
        ),
    )
    recipient_agent: str = None  # Will be automatically converted to the Agent instance
    file_ids: list[str] = None
    additional_instructions: str = None
    attachments: list[Attachment] = []
    message_files: list[str] = None


def add_agent_validator(model, agent_instances):
    class ModifiedRequest(model):
        @field_validator("recipient_agent")
        def validate_recipient_agent(cls, v):
            if v is not None:
                if v not in agent_instances:
                    raise ValueError(f"Invalid agent name. Available agents: {list(agent_instances.keys())}")
                return agent_instances[v]
            return v

    return ModifiedRequest

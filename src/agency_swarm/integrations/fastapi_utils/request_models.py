from typing import Any

from pydantic import BaseModel, field_validator


class AttachmentTool(BaseModel):
    type: str


class Attachment(BaseModel):
    file_id: str
    tools: list[AttachmentTool]


class BaseRequest(BaseModel):
    message: str
    recipient_agent: str = None  # Will be automatically converted to the Agent instance
    chat_id: str = None
    context_override: dict[str, Any] = None
    hooks_override: str = None

    # Not yet implemented
    # files: list[str] = None
    # additional_instructions: str = None
    # attachments: List[Attachment] = []
    # tool_choice: dict = None
    # response_format: dict = None


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

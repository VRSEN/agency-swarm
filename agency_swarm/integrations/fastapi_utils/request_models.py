from typing import List
from pydantic import BaseModel, field_validator


class AttachmentTool(BaseModel):
    type: str


class Attachment(BaseModel):
    file_id: str
    tools: List[AttachmentTool]


class BaseRequest(BaseModel):
    message: str
    message_files: List[str] = None
    recipient_agent: str = None # Will be automatically converted to the Agent instance
    additional_instructions: str = None
    attachments: List[Attachment] = []
    tool_choice: dict = None
    response_format: dict = None

def add_agent_validator(model, agent_instances):
    class ModifiedRequest(model):
        @field_validator('recipient_agent')
        def validate_recipient_agent(cls, v):
            if v is not None:
                if v not in agent_instances:
                    raise ValueError(f"Invalid agent name. Available agents: {list(agent_instances.keys())}")
                return agent_instances[v]
            return v
    return ModifiedRequest

from typing import List

from pydantic import BaseModel, Field, field_validator


class AttachmentTool(BaseModel):
    type: str


class Attachment(BaseModel):
    file_id: str
    tools: List[AttachmentTool]


class BaseRequest(BaseModel):
    message: str
    message_files: List[str] = None
    recipient_agent: str = None  # Will be automatically converted to the Agent instance
    additional_instructions: str = None
    attachments: List[Attachment] = []
    tool_choice: dict = None
    response_format: dict = None
    threads: dict = Field(
        None, # Not providing this parameter will keep the existing threads
        description="The structure should follow the pattern used in threads callbacks",
        examples=[
            {
                "CEOAgent": {
                    "WorkerAgent": "thread_eUWgjmN05vvYmqn9wQXhGKao",
                    "HelperAgent": None, # Creates a new thread if None provided
                },
                "WorkerAgent": {"HelperAgent": "thread_WOSPRx1xVF9os41t6ph4xEoJ"},
                "main_thread": "thread_t2ggvsmZYzOTM05e4n3O7lIl",
            },
            {} # Providing empty dict will reset all threads and start a new chat
        ],
    )


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

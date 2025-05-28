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
                    "WorkerAgent": "thread_asdAQWDadKHYTdi0uasndu8iub",
                    "HelperAgent": None, # Creates a new thread if None provided
                },
                "WorkerAgent": {"HelperAgent": "thread_opjknbnaf9198b1fv1089b3A"},
                "main_thread": "thread_Qiofn9HasdTYUCV6123v1f8v",
            },
            {
                "CEOAgent": {
                    "WorkerAgent": "thread_asdalndoasndi0uasndu8iub",
                    "HelperAgent": None, # Creates a new thread if None provided
                },
                # Providing a partial dict will reset threads of non-specified agents
                "main_thread": "thread_Qiofn9HasdTYUCV6123v1f8v",
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
        
        @field_validator("threads")
        def validate_threads(cls, v):
            if v is not None:
                for agent, threads in v.items():
                    if agent not in agent_instances and agent != "main_thread":
                        raise ValueError(f"Invalid agent name. Available agents: {list(agent_instances.keys())+['main_thread']}")
                    if isinstance(threads, dict):
                        for other_agent, thread_id in threads.items():
                            print(f"other_agent: {other_agent}, thread_id: {thread_id}")
                            if other_agent not in agent_instances:
                                raise ValueError(
                                    f"Invalid agent name. Available agents: {list(agent_instances.keys())+['main_thread']}"
                                )
            return v

    return ModifiedRequest

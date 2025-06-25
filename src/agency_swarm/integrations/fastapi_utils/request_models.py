from typing import Any, List

from agents import TResponseInputItem
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

try:
    from ag_ui.core import Context, Message, Tool
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "ag_ui.core is required for the OpenAI→AG-UI adapter. Install with `pip install ag-ui-protocol`."
    ) from exc


class ConversationThread(BaseModel):
    items: list[TResponseInputItem]
    metadata: dict[str, Any] = Field(default_factory=dict)

class ConfiguredBaseModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        ser_json_by_alias=True
    )

# Mockup of the ag-ui RunAgentInput with added chat_history field
class RunAgentInput(ConfiguredBaseModel):
    """
    Input for running an agent.
    """
    thread_id: str
    run_id: str
    state: Any
    messages: List[Message]
    tools: List[Tool]
    context: List[Context]
    forwarded_props: Any
    chat_history: dict[str, ConversationThread] = Field(
        None,
        description=(
            "Entire chat history containing previous messages across all threads. "
            "Should be provided in a form of {'thread_1': ConversationThread, 'thread_2': ConversationThread, ...}"
        ),
    )


class BaseRequest(BaseModel):
    message: str
    chat_history: dict[str, ConversationThread] = Field(
        None,
        description=(
            "Entire chat history containing previous messages across all threads. "
            "Should be provided in a form of {'thread_1': ConversationThread, 'thread_2': ConversationThread, ...}"
        ),
    )
    recipient_agent: str = None
    file_ids: list[str] = None
    additional_instructions: str = None


def add_agent_validator(model, agent_instances):
    class ModifiedRequest(model):
        @field_validator("recipient_agent")
        def validate_recipient_agent(cls, v):
            if v is not None:
                if v not in agent_instances:
                    raise ValueError(f"Invalid agent name. Available agents: {list(agent_instances.keys())}")
                return v  # No longer converted to Agent instance, let _resolve_agent handle it
            return v

    return ModifiedRequest

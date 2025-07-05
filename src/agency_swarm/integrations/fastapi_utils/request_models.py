from typing import Any

from agents import TResponseInputItem
from pydantic import BaseModel, Field, field_validator

try:
    from ag_ui.core import RunAgentInput
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "ag_ui.core is required for the OpenAI→AG-UI adapter. Install with `pip install ag-ui-protocol`."
    ) from exc


class ConversationThread(BaseModel):
    items: list[TResponseInputItem]
    metadata: dict[str, Any] = Field(default_factory=dict)


# Extended version of the ag-ui RunAgentInput with added chat_history field
class RunAgentInputCustom(RunAgentInput):
    """
    Input for running an agent.
    """

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


if __name__ == "__main__":
    print(
        RunAgentInputCustom(
            thread_id="test",
            run_id="test",
            state=None,
            messages=[],
            tools=[],
            context=[],
            forwarded_props=None,
            chat_history="test",
        )
    )

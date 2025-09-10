from typing import Any

from pydantic import BaseModel, Field, field_validator

try:
    from ag_ui.core import RunAgentInput
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "ag_ui.core is required for the OpenAI→AG-UI adapter. Install with `pip install ag-ui-protocol`."
    ) from exc


# Extended version of the ag-ui RunAgentInput with added chat_history and additional_instructions fields
class RunAgentInputCustom(RunAgentInput):
    """Input for running an agent."""

    chat_history: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Entire chat history as a flat list of messages. "
            "Each message should contain 'agent', 'callerAgent', 'timestamp' and other OpenAI fields."
        ),
    )
    additional_instructions: str | None = None


class BaseRequest(BaseModel):
    message: str
    chat_history: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Entire chat history as a flat list of messages. "
            "Each message should contain 'agent', 'callerAgent', 'timestamp' and other OpenAI fields."
        ),
    )
    recipient_agent: str | None = None
    file_ids: list[str] | None = None
    file_urls: dict[str, str] | None = Field(
        default=None,
        description=(
            "List of downloadable file urls to be use as file attachments. "
            "Should be provided in a form of {'file_name_1': 'download_url_1', 'file_name_2': 'download_url_2', ...}"
        ),
    )
    additional_instructions: str | None = None


class LogRequest(BaseModel):
    """Request model for retrieving logs."""

    log_id: str = Field(..., description="The log ID to retrieve")


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
            chat_history=[],
        )
    )

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

try:
    from ag_ui.core import RunAgentInput
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "ag_ui.core is required for the OpenAI→AG-UI adapter. Install with `pip install ag-ui-protocol`."
    ) from exc


# Extended version of the ag-ui RunAgentInput with additional fields
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
    user_context: dict[str, Any] | None = Field(
        default=None,
        description="Structured context merged into MasterContext.user_context for this run only.",
    )
    file_ids: list[str] | None = None
    file_urls: dict[str, str] | None = Field(
        default=None,
        description=(
            "File attachments as URLs or absolute local paths. "
            "Format: {'file_name': 'url_or_path', ...}. "
            "Supports http(s) URLs and absolute local paths (e.g., '/home/user/doc.pdf') "
            "when the server is configured with allowed local file directories."
        ),
    )


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
            "File attachments as URLs or absolute local paths. "
            "Format: {'file_name': 'url_or_path', ...}. "
            "Supports http(s) URLs and absolute local paths (e.g., '/home/user/doc.pdf') "
            "when the server is configured with allowed local file directories."
        ),
    )
    additional_instructions: str | None = None
    user_context: dict[str, Any] | None = Field(
        default=None,
        description="Structured context merged into MasterContext.user_context for this run only.",
    )
    generate_chat_name: bool | None = Field(
        default=False, description="Generate a fitting chat name for the user input."
    )


class LogRequest(BaseModel):
    """Request model for retrieving logs."""

    log_id: str = Field(..., description="The log ID to retrieve")


class CancelRequest(BaseModel):
    """Request model for cancelling an active streaming run."""

    run_id: str = Field(..., description="The run ID returned by the streaming endpoint meta event.")
    cancel_mode: Literal["immediate", "after_turn"] | None = Field(
        default=None,
        description=(
            'Optional cancel mode. Use "immediate" to stop right away '
            'or "after_turn" to finish the current turn before stopping.'
        ),
    )


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

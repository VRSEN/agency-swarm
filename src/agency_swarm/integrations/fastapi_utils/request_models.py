import logging
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, WithJsonSchema, field_validator

try:
    from ag_ui.core import RunAgentInput
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "ag_ui.core is required for the OpenAI→AG-UI adapter. Install with `pip install ag-ui-protocol`."
    ) from exc

# Use LiteLLM's provider enum for validation when available
try:
    from litellm import LlmProviders as LiteLLMProvider

    _LITELLM_INSTALLED = True
except ImportError:
    LiteLLMProvider = str  # type: ignore[misc, assignment]
    _LITELLM_INSTALLED = False

logger = logging.getLogger(__name__)

_MESSAGE_SCHEMA: dict[str, Any] = {
    "anyOf": [
        {"type": "string"},
        {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["role", "content"],
                "properties": {
                    "role": {"type": "string", "enum": ["user", "system", "developer"]},
                    "type": {"type": "string", "const": "message"},
                    "status": {"type": "string", "enum": ["in_progress", "completed", "incomplete"]},
                    "content": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "oneOf": [
                                {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["type", "text"],
                                    "properties": {
                                        "type": {"type": "string", "const": "input_text"},
                                        "text": {"type": "string"},
                                    },
                                },
                                {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["type", "detail"],
                                    "properties": {
                                        "type": {"type": "string", "const": "input_image"},
                                        "detail": {"type": "string", "enum": ["low", "high", "auto"]},
                                        "file_id": {"type": ["string", "null"]},
                                        "image_url": {"type": ["string", "null"]},
                                    },
                                    "anyOf": [
                                        {"required": ["file_id"]},
                                        {"required": ["image_url"]},
                                    ],
                                },
                                {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["type"],
                                    "properties": {
                                        "type": {"type": "string", "const": "input_file"},
                                        "file_data": {"type": "string"},
                                        "file_id": {"type": ["string", "null"]},
                                        "file_url": {"type": "string"},
                                        "filename": {"type": "string"},
                                    },
                                    "anyOf": [
                                        {"required": ["file_data"]},
                                        {"required": ["file_id"]},
                                        {"required": ["file_url"]},
                                    ],
                                },
                            ]
                        },
                    },
                },
            },
        },
    ]
}

MessageInput = Annotated[str | list[dict[str, Any]], WithJsonSchema(_MESSAGE_SCHEMA)]

_MESSAGE_KEYS = {"role", "content", "type", "status"}
_MESSAGE_ROLES = {"user", "system", "developer"}
_MESSAGE_STATUSES = {"in_progress", "completed", "incomplete"}
_CONTENT_KEYS = {
    "input_text": {"type", "text"},
    "input_image": {"type", "detail", "file_id", "image_url"},
    "input_file": {"type", "file_data", "file_id", "file_url", "filename"},
}
_IMAGE_DETAILS = {"low", "high", "auto"}


class ClientConfig(BaseModel):
    """Configuration for overriding the OpenAI client per-request."""

    base_url: str | None = Field(
        default=None,
        description="OpenAI-compatible API base URL override.",
    )
    api_key: str | None = Field(
        default=None,
        description="OpenAI API key override.",
    )
    default_headers: dict[str, str] | None = Field(
        default=None,
        description=(
            "Additional default headers to include in OpenAI API requests for this run only. "
            "Merged with any existing client default headers; per-request values override existing keys."
        ),
    )
    litellm_keys: dict[LiteLLMProvider, str] | None = Field(
        default=None,
        description=(
            "Provider-specific API keys for LiteLLM models. "
            "Key = provider from model path (e.g., 'anthropic', 'gemini', 'azure', 'xai'). "
            "If not provided (or provider not found), non-OpenAI providers will fall back to their environment "
            "variables; OpenAI-compatible providers may fall back to 'api_key'."
        ),
    )
    model: str | None = Field(
        default=None,
        description=(
            "If set, every agent in the agency uses this model name for the request only "
            "(same string forms as Agent.model: OpenAI names, 'openai/…', 'litellm/…', provider paths, etc.)."
        ),
    )

    @field_validator("litellm_keys")
    @classmethod
    def validate_litellm_installed(cls, v: dict | None) -> dict | None:
        """Drop litellm_keys with a warning when litellm is not installed.

        Older bridges or callers that always forward `litellm_keys` should not get a 422
        when the receiving environment lacks the `[litellm]` extra. The keys are useless
        without the dependency, so we drop them and let downstream code fall back to
        OpenAI-only behavior.
        """
        if v is not None and not _LITELLM_INSTALLED:
            logger.warning(
                "Ignoring client_config.litellm_keys: litellm is not installed. "
                "Install with `pip install 'openai-agents[litellm]'` to enable provider-key routing."
            )
            return None
        return v


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
    client_config: ClientConfig | None = Field(
        default=None,
        description="Override client configuration (base_url, api_key, litellm_keys, model) for this request only.",
    )


class BaseRequest(BaseModel):
    message: MessageInput = Field(
        ...,
        description=(
            "User message to start or continue the conversation. Accepts plain text or structured Responses "
            "input messages, including inline input_image/input_file content."
        ),
    )
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
    client_config: ClientConfig | None = Field(
        default=None,
        description="Override client configuration (base_url, api_key, litellm_keys, model) for this request only.",
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: MessageInput) -> MessageInput:
        if isinstance(v, str):
            return v
        if not v:
            raise ValueError("message must contain at least one structured Responses message")
        for item in v:
            _validate_structured_message(item)
        return v


def _validate_structured_message(message: dict[str, Any]) -> None:
    extra_keys = set(message) - _MESSAGE_KEYS
    if extra_keys:
        raise ValueError(f"structured message contains unsupported fields: {sorted(extra_keys)}")

    role = message.get("role")
    if role not in _MESSAGE_ROLES:
        raise ValueError("structured message role must be one of user, system, or developer")

    if "type" in message and message["type"] != "message":
        raise ValueError("structured message type must be 'message' when provided")

    if "status" in message and message["status"] not in _MESSAGE_STATUSES:
        raise ValueError("structured message status must be one of in_progress, completed, or incomplete")

    content = message.get("content")
    if not isinstance(content, list) or not content:
        raise ValueError("structured message content must contain at least one item")

    for item in content:
        _validate_structured_content(item)


def _validate_structured_content(content: Any) -> None:
    if not isinstance(content, dict):
        raise ValueError("structured message content items must be objects")

    content_type = content.get("type")
    if content_type not in _CONTENT_KEYS:
        raise ValueError("structured message content type must be input_text, input_image, or input_file")

    extra_keys = set(content) - _CONTENT_KEYS[content_type]
    if extra_keys:
        raise ValueError(f"structured message content contains unsupported fields: {sorted(extra_keys)}")

    if content_type == "input_text":
        _validate_text_content(content)
    elif content_type == "input_image":
        _validate_image_content(content)
    else:
        _validate_file_content(content)


def _validate_text_content(content: dict[str, Any]) -> None:
    if not isinstance(content.get("text"), str):
        raise ValueError("input_text content requires string text")


def _validate_image_content(content: dict[str, Any]) -> None:
    if content.get("detail") not in _IMAGE_DETAILS:
        raise ValueError("input_image content requires detail of low, high, or auto")
    if not _has_non_empty_string(content, "file_id") and not _has_non_empty_string(content, "image_url"):
        raise ValueError("input_image content requires file_id or image_url")


def _validate_file_content(content: dict[str, Any]) -> None:
    if not any(_has_non_empty_string(content, key) for key in ("file_data", "file_id", "file_url")):
        raise ValueError("input_file content requires file_data, file_id, or file_url")
    if "filename" in content and not isinstance(content["filename"], str):
        raise ValueError("input_file content filename must be a string")


def _has_non_empty_string(value: dict[str, Any], key: str) -> bool:
    return isinstance(value.get(key), str) and bool(value[key])


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

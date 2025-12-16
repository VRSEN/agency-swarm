"""Agent module constants extracted to keep files under size limits (no behavior change)."""

from typing import Literal

# Combine old and new params for easier checking later
AGENT_PARAMS = {
    # New/Current
    "files_folder",
    "tools_folder",
    "schemas_folder",
    "api_headers",
    "api_params",
    "description",
    "include_search_results",
    "validation_attempts",
    "throw_input_guardrail_error",
    "voice",
    # Old/Deprecated (to check in kwargs)
    "id",
    "tool_resources",
    "file_ids",
    "reasoning_effort",
    "examples",
    "file_search",
    "refresh_from_id",
}

# Constants for dynamic tool creation
MESSAGE_PARAM = "message"

# Canonical realtime voice options mirrored from openai-agents SDK v0.4.1
AGENT_REALTIME_VOICES = (
    "alloy",
    "ash",
    "coral",
    "echo",
    "fable",
    "onyx",
    "nova",
    "sage",
    "shimmer",
)

AgentVoice = Literal[
    "alloy",
    "ash",
    "coral",
    "echo",
    "fable",
    "onyx",
    "nova",
    "sage",
    "shimmer",
]

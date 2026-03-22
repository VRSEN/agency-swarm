"""Agent module constants extracted to keep files under size limits (no behavior change)."""

from typing import Literal

AGENT_PARAMS = {
    "files_folder",
    "tools_folder",
    "schemas_folder",
    "api_headers",
    "api_params",
    "description",
    "conversation_starters",
    "quick_replies",
    "cache_conversation_starters",
    "include_search_results",
    "include_web_search_sources",
    "validation_attempts",
    "raise_input_guardrail_error",
    "voice",
}

# Constants for dynamic tool creation
MESSAGE_PARAM = "message"

# Canonical realtime voice options supported by Agency Swarm integrations.
AGENT_OPENAI_REALTIME_VOICES = (
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

AGENT_XAI_REALTIME_VOICES = (
    "ara",
    "eve",
    "leo",
    "rex",
    "sal",
)

AGENT_REALTIME_VOICES = AGENT_OPENAI_REALTIME_VOICES + AGENT_XAI_REALTIME_VOICES

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
    "ara",
    "eve",
    "leo",
    "rex",
    "sal",
]

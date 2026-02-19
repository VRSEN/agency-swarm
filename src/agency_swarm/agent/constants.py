"""Agent module constants extracted to keep files under size limits (no behavior change)."""

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
    "throw_input_guardrail_error",
}

# Constants for dynamic tool creation
MESSAGE_PARAM = "message"

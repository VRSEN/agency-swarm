"""Agent module constants extracted to keep files under size limits (no behavior change)."""

# Override the Agents SDK default model (gpt-4.1) to prevent infinite tool-call
# loops observed with that model in handoff workflows.
FRAMEWORK_DEFAULT_MODEL = "gpt-5.4-mini"

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
}

# Constants for dynamic tool creation
MESSAGE_PARAM = "message"

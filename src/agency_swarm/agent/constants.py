"""Agent module constants extracted to keep files under size limits (no behavior change)."""

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

"""Coverage-focused tests for agent module constants."""

from agency_swarm.agent import constants


def test_agent_params_includes_expected_entries() -> None:
    """Ensure both legacy and modern parameters remain exposed."""
    required = {
        "files_folder",
        "tools_folder",
        "schemas_folder",
        "api_headers",
        "api_params",
        "description",
        "include_search_results",
        "validation_attempts",
        "throw_input_guardrail_error",
        "id",
        "tool_resources",
        "file_ids",
        "reasoning_effort",
        "examples",
        "file_search",
        "refresh_from_id",
    }

    assert required.issubset(constants.AGENT_PARAMS)


def test_message_param_remains_stable() -> None:
    """MESSAGE_PARAM should remain the canonical message field."""
    assert constants.MESSAGE_PARAM == "message"

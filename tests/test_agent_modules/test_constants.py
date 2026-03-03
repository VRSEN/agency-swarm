from agency_swarm.agent.constants import AGENT_PARAMS, MESSAGE_PARAM


def test_agent_constants_export_expected_values() -> None:
    assert MESSAGE_PARAM == "message"
    assert "conversation_starters" in AGENT_PARAMS
    assert "quick_replies" in AGENT_PARAMS
    assert "cache_conversation_starters" in AGENT_PARAMS

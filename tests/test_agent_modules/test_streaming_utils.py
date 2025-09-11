from unittest.mock import MagicMock

from agency_swarm.streaming.utils import add_agent_name_to_event, ensure_event_agent_metadata


def test_add_agent_name_to_event_dict_basic():
    evt = {"event": "text"}
    out = add_agent_name_to_event(evt, "AgentA", None)
    assert out["agent"] == "AgentA"
    assert out["callerAgent"] is None
    assert "agent_run_id" not in out and "parent_run_id" not in out


def test_add_agent_name_to_event_dict_structured_with_type_and_run_ids():
    evt = {"type": "raw_response_event"}
    out = add_agent_name_to_event(evt, "AgentA", "CallerX", agent_run_id="ARID", parent_run_id="PRID")
    assert out["agent"] == "AgentA"
    assert out["callerAgent"] == "CallerX"
    assert out["agent_run_id"] == "ARID"
    assert out["parent_run_id"] == "PRID"


def test_add_agent_name_to_event_object_basic_attrs():
    evt = MagicMock()
    # no type attr: run ids should not be attached
    out = add_agent_name_to_event(evt, "AgentB", None)
    assert getattr(out, "agent", None) == "AgentB"
    assert getattr(out, "callerAgent", "SENTINEL") is None
    assert not hasattr(out, "agent_run_id") and not hasattr(out, "parent_run_id")


def test_add_agent_name_to_event_object_structured_with_type_and_run_ids():
    evt = MagicMock()
    type(evt).type = "run_item_stream_event"
    out = add_agent_name_to_event(evt, "AgentB", "CallerY", agent_run_id="AR2", parent_run_id="PR2")
    assert out.agent == "AgentB"
    assert out.callerAgent == "CallerY"
    assert out.agent_run_id == "AR2"
    assert out.parent_run_id == "PR2"


# Note: call_id/item_id extraction is an internal detail and not part of public/docs usage.
# We intentionally do not test these paths here to keep tests aligned with documented behavior.


def test_ensure_event_agent_metadata_dict_fill_missing_not_overwrite():
    evt = {"agent": "Existing", "event": "text"}
    out = ensure_event_agent_metadata(evt, "NewAgent", "CallerZ")
    # agent preserved, caller added
    assert out["agent"] == "Existing"
    assert out["callerAgent"] == "CallerZ"


def test_ensure_event_agent_metadata_object_fill_missing_and_preserve():
    evt = MagicMock()
    out = ensure_event_agent_metadata(evt, "AgentF", None)
    assert getattr(out, "agent", None) == "AgentF"
    assert getattr(out, "callerAgent", "SENTINEL") is None
    # Preserve existing
    evt2 = MagicMock()
    type(evt2).agent = "KeepMe"
    out2 = ensure_event_agent_metadata(evt2, "WillNotOverwrite", "CallerK")
    assert out2.agent == "KeepMe"
    assert out2.callerAgent == "CallerK"

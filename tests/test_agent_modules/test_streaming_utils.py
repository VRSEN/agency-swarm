from agency_swarm.streaming.utils import add_agent_name_to_event


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
    # Create a simple object without pre-existing attributes
    class SimpleEvent:
        pass

    evt = SimpleEvent()
    # no type attr: run ids should not be attached
    out = add_agent_name_to_event(evt, "AgentB", None)
    assert out.agent == "AgentB"
    assert out.callerAgent is None
    assert not hasattr(out, "agent_run_id") and not hasattr(out, "parent_run_id")


def test_add_agent_name_to_event_object_structured_with_type_and_run_ids():
    # Create a simple object with type attribute
    class StructuredEvent:
        def __init__(self):
            self.type = "run_item_stream_event"

    evt = StructuredEvent()
    out = add_agent_name_to_event(evt, "AgentB", "CallerY", agent_run_id="AR2", parent_run_id="PR2")
    assert out.agent == "AgentB"
    assert out.callerAgent == "CallerY"
    assert out.agent_run_id == "AR2"
    assert out.parent_run_id == "PR2"


# Note: call_id/item_id extraction is an internal detail and not part of public/docs usage.
# We intentionally do not test these paths here to keep tests aligned with documented behavior.


def test_add_agent_name_to_event_dict_non_destructive_preserves_existing():
    """Test that add_agent_name_to_event preserves existing agent/callerAgent values (non-destructive)."""
    evt = {"agent": "ExistingAgent", "event": "text"}
    out = add_agent_name_to_event(evt, "NewAgent", "NewCaller")
    # Existing agent should be preserved
    assert out["agent"] == "ExistingAgent"
    # callerAgent should be added since it wasn't present
    assert out["callerAgent"] == "NewCaller"


def test_add_agent_name_to_event_dict_fills_missing_fields():
    """Test that add_agent_name_to_event fills missing agent/callerAgent fields."""
    evt = {"event": "text"}
    out = add_agent_name_to_event(evt, "AgentX", "CallerY")
    assert out["agent"] == "AgentX"
    assert out["callerAgent"] == "CallerY"


def test_add_agent_name_to_event_object_non_destructive_preserves_existing():
    """Test that add_agent_name_to_event preserves existing attributes on objects."""

    class EventWithAgent:
        def __init__(self):
            self.agent = "ExistingAgent"

    evt = EventWithAgent()
    out = add_agent_name_to_event(evt, "NewAgent", "NewCaller")
    # Existing agent should be preserved
    assert out.agent == "ExistingAgent"
    # callerAgent should be set since it wasn't present
    assert out.callerAgent == "NewCaller"


def test_add_agent_name_to_event_object_fills_missing_attributes():
    """Test that add_agent_name_to_event adds missing attributes on objects."""

    class EmptyEvent:
        pass

    evt = EmptyEvent()
    out = add_agent_name_to_event(evt, "AgentZ", None)
    assert out.agent == "AgentZ"
    assert out.callerAgent is None


def test_add_agent_name_to_event_preserves_run_ids():
    """Test that add_agent_name_to_event preserves existing run_id fields on structured events."""
    evt = {"type": "run_item_stream_event", "agent_run_id": "ExistingRunId", "event": "text"}
    out = add_agent_name_to_event(evt, "AgentA", "CallerB", agent_run_id="NewRunId", parent_run_id="NewParentId")
    # Existing run_id should be preserved
    assert out["agent_run_id"] == "ExistingRunId"
    # parent_run_id should be added since it wasn't present
    assert out["parent_run_id"] == "NewParentId"

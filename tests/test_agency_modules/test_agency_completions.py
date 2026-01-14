from agency_swarm import Agency, Agent


def test_agency_does_not_expose_deprecated_completion_helpers() -> None:
    agency = Agency(Agent(name="EntryPoint", instructions="test"))
    assert not hasattr(agency, "get_completion")
    assert not hasattr(agency, "get_completion_stream")

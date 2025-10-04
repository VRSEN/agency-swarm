"""Integration tests for the FastAPI metadata endpoint."""

import pytest

pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient

from agency_swarm import Agency, Agent, run_fastapi
from agency_swarm.integrations.fastapi_utils import endpoint_handlers


@pytest.fixture
def agency_factory():
    """Provide a simple agency factory for FastAPI tests."""

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="MetadataAgent", instructions="Return metadata")
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    return create_agency


def test_metadata_endpoint_includes_version(monkeypatch, agency_factory):
    """Verify that the metadata endpoint includes the agency-swarm version."""

    expected_version = "9.9.9"
    monkeypatch.setattr(endpoint_handlers, "_get_agency_swarm_version", lambda: expected_version)

    app = run_fastapi(agencies={"test_agency": agency_factory}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.get("/test_agency/get_metadata")

    assert response.status_code == 200
    payload = response.json()
    assert payload["agency_swarm_version"] == expected_version


def test_metadata_endpoint_omits_missing_version(monkeypatch, agency_factory):
    """Ensure missing version information is not added to the payload."""

    monkeypatch.setattr(endpoint_handlers, "_get_agency_swarm_version", lambda: None)

    app = run_fastapi(agencies={"test_agency": agency_factory}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.get("/test_agency/get_metadata")

    assert response.status_code == 200
    payload = response.json()
    assert "agency_swarm_version" not in payload

import pytest
from fastapi.testclient import TestClient

from agency_swarm import Agency, Agent
from agency_swarm.integrations.fastapi import run_fastapi


@pytest.fixture
def dummy_agency():
    agent = Agent(name="TestAgent", model="gpt-5.4-mini")
    return {"test": lambda **kwargs: Agency(agent)}


def test_cors_wildcard_disables_credentials(dummy_agency):
    """
    Test that when 'cors_origins' contains '*', the Access-Control-Allow-Credentials header is NOT present.
    """
    app = run_fastapi(agencies=dummy_agency, return_app=True)
    client = TestClient(app)

    # Preflight request
    headers = {
        "Origin": "https://random-site.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    }
    response = client.options("/test/get_response", headers=headers)

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"
    # Credentials should be absent when origin is wildcard
    assert "access-control-allow-credentials" not in response.headers

    # Simple response should also omit credentials for wildcard origins
    simple_response = client.post(
        "/test/get_response",
        headers={"Origin": "https://random-site.com"},
        json={},
    )
    assert simple_response.headers.get("access-control-allow-origin") == "*"
    assert "access-control-allow-credentials" not in simple_response.headers


def test_cors_explicit_origins_keeps_credentials(dummy_agency):
    """
    Test that when specific origins are provided, Access-Control-Allow-Credentials IS present.
    """
    origin = "https://example.com"
    app = run_fastapi(agencies=dummy_agency, cors_origins=[origin], return_app=True)
    client = TestClient(app)

    headers = {
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    }
    response = client.options("/test/get_response", headers=headers)

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin
    # Credentials should be present for specific origins
    assert response.headers.get("access-control-allow-credentials") == "true"

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from agents import HostedMCPTool
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.testclient import TestClient
from openai.types.responses.tool_param import Mcp

from agency_swarm import Agency, Agent, enable_hosted_mcp_tool_oauth, run_fastapi
from agency_swarm.integrations.fastapi_utils import endpoint_handlers
from agency_swarm.integrations.fastapi_utils.oauth_support import OAuthStateRegistry
from agency_swarm.mcp.oauth import MCPServerOAuth
from tests.test_agency_modules._response_test_helpers import _make_agent


def _test_oauth_user_id() -> str:
    return "test-user"


def _plain_agency(
    load_threads_callback: Callable[[], list[dict[str, Any]]] | None = None,
    save_threads_callback: Callable[[list[dict[str, Any]]], None] | None = None,
) -> Agency:
    return Agency(
        _make_agent("TestAgent"),
        load_threads_callback=load_threads_callback,
        save_threads_callback=save_threads_callback,
    )


def _oauth_agency(
    load_threads_callback: Callable[[], list[dict[str, Any]]] | None = None,
    save_threads_callback: Callable[[list[dict[str, Any]]], None] | None = None,
) -> Agency:
    server = MCPServerOAuth(
        url="http://localhost:9999/mcp",
        name="oauth-demo",
        client_id="client-id",
        client_secret="client-secret",
    )
    return Agency(
        Agent(name="TestAgent", instructions="Base instructions", mcp_servers=[server]),
        load_threads_callback=load_threads_callback,
        save_threads_callback=save_threads_callback,
    )


def _hosted_oauth_agency(
    load_threads_callback: Callable[[], list[dict[str, Any]]] | None = None,
    save_threads_callback: Callable[[list[dict[str, Any]]], None] | None = None,
) -> Agency:
    hosted_tool = enable_hosted_mcp_tool_oauth(
        HostedMCPTool(
            tool_config=Mcp(
                type="mcp",
                server_label="notion",
                server_url="https://mcp.notion.com/mcp",
            )
        )
    )
    return Agency(
        Agent(name="TestAgent", instructions="Base instructions", tools=[hosted_tool]),
        load_threads_callback=load_threads_callback,
        save_threads_callback=save_threads_callback,
    )


def _stateful_factory(
    request_factory: Callable[..., Agency],
) -> tuple[Callable[..., Agency], list[str]]:
    calls: list[str] = []

    def factory(load_threads_callback=None, save_threads_callback=None) -> Agency:
        phase = "preview" if not calls else "request"
        calls.append(phase)
        selected_factory = _plain_agency if phase == "preview" else request_factory
        return selected_factory(
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    return factory, calls


def _post_request(client: TestClient, endpoint_kind: str):
    if endpoint_kind == "response":
        return client.post("/test_agency/get_response", json={"message": "hello"})
    if endpoint_kind == "stream":
        return client.post("/test_agency/get_response_stream", json={"message": "hello"})

    payload: dict[str, Any] = {
        "thread_id": "test-thread",
        "run_id": "test-run",
        "state": None,
        "messages": [],
        "tools": [],
        "context": [],
        "forwardedProps": None,
    }
    if endpoint_kind == "agui_messages":
        payload["messages"] = [{"id": "message-1", "role": "user", "content": "hello"}]
    else:
        payload["chat_history"] = [{"role": "user", "content": "hello"}]
    return client.post("/test_agency/get_response_stream", json=payload)


def test_oauth_enabled_fastapi_requires_user_id_dependency() -> None:
    with pytest.raises(ValueError, match="oauth_user_id_dependency"):
        run_fastapi(
            agencies={"test_agency": _oauth_agency},
            return_app=True,
            app_token_env="",
        )


def test_spoofed_user_header_cannot_select_oauth_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_user_ids: list[str | None] = []
    original_prepare = endpoint_handlers._prepare_oauth_runtime

    def capture_user_id(agency, runtime, user_id):
        seen_user_ids.append(user_id)
        return original_prepare(agency, runtime, user_id)

    monkeypatch.setattr(endpoint_handlers, "_prepare_oauth_runtime", capture_user_id)
    app = run_fastapi(
        agencies={"test_agency": _oauth_agency},
        return_app=True,
        app_token_env="",
        oauth_user_id_dependency=lambda: "configured-user",
    )
    assert app is not None
    app.dependency_overrides[app.state.oauth_user_id_dependency] = lambda: "authenticated-user"

    response = TestClient(app).post(
        "/test_agency/get_response",
        headers={"X-User-Id": "victim-user"},
        json={"message": "hello"},
    )

    assert response.status_code == 400
    assert seen_user_ids == ["authenticated-user"]


def test_oauth_callback_uses_state_and_status_requires_owner() -> None:
    registry = OAuthStateRegistry()
    asyncio.run(
        registry.record_redirect(
            state="owned-state",
            auth_url="https://idp.example.com/authorize?state=owned-state",
            server_name="oauth-demo",
            user_id="owner-user",
        )
    )
    security = HTTPBearer()

    async def authenticated_user_id(
        credentials: HTTPAuthorizationCredentials = Depends(security),  # noqa: B008
    ) -> str:
        users = {"owner-token": "owner-user", "other-token": "other-user"}
        user_id = users.get(credentials.credentials)
        if user_id is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return user_id

    app = run_fastapi(
        agencies={"test_agency": _oauth_agency},
        return_app=True,
        app_token_env="",
        oauth_registry=registry,
        oauth_user_id_dependency=authenticated_user_id,
    )
    assert app is not None
    client = TestClient(app)

    callback = client.get("/auth/callback?state=owned-state&code=code-123")
    owner_status = client.get("/auth/status/owned-state", headers={"Authorization": "Bearer owner-token"})
    other_status = client.get("/auth/status/owned-state", headers={"Authorization": "Bearer other-token"})

    assert callback.status_code == 200
    assert owner_status.status_code == 200
    assert owner_status.json()["status"] == "authorized"
    assert other_status.status_code == 404


def test_oauth_callback_rejects_late_code_for_terminal_flow() -> None:
    registry = OAuthStateRegistry()
    asyncio.run(
        registry.record_redirect(
            state="timed-out-state",
            auth_url="https://idp.example.com/authorize?state=timed-out-state",
            server_name="oauth-demo",
            user_id="owner-user",
        )
    )
    asyncio.run(registry.set_timeout(state="timed-out-state"))
    app = run_fastapi(
        agencies={"test_agency": _oauth_agency},
        return_app=True,
        app_token_env="",
        oauth_registry=registry,
        oauth_user_id_dependency=lambda: "owner-user",
    )
    assert app is not None
    client = TestClient(app)

    callback = client.get("/auth/callback?state=timed-out-state&code=late-code")
    status = client.get("/auth/status/timed-out-state")

    assert callback.status_code == 400
    assert callback.json()["detail"] == "OAuth flow is not pending: state=timed-out-state, status=timeout"
    assert status.status_code == 200
    assert status.json()["status"] == "timeout"


@pytest.mark.parametrize("endpoint_kind", ["response", "stream", "agui_messages", "agui_history"])
def test_request_time_oauth_factory_requires_startup_oauth_config(endpoint_kind: str) -> None:
    agency_factory, calls = _stateful_factory(_oauth_agency)
    app = run_fastapi(
        agencies={"test_agency": agency_factory},
        return_app=True,
        app_token_env="",
        enable_agui=endpoint_kind.startswith("agui"),
    )
    assert app is not None
    client = TestClient(app, raise_server_exceptions=False)

    response = _post_request(client, endpoint_kind)

    assert response.status_code == 500
    assert "oauth_user_id_dependency" in response.json()["detail"]
    assert calls == ["preview", "request"]


def test_request_time_hosted_oauth_factory_requires_startup_oauth_config() -> None:
    agency_factory, calls = _stateful_factory(_hosted_oauth_agency)
    app = run_fastapi(
        agencies={"test_agency": agency_factory},
        return_app=True,
        app_token_env="",
    )
    assert app is not None

    response = TestClient(app, raise_server_exceptions=False).post(
        "/test_agency/get_response",
        json={"message": "hello"},
    )

    assert response.status_code == 500
    assert "oauth_user_id_dependency" in response.json()["detail"]
    assert calls == ["preview", "request"]


def test_request_time_non_oauth_factory_remains_supported() -> None:
    agency_factory, calls = _stateful_factory(_plain_agency)
    app = run_fastapi(
        agencies={"test_agency": agency_factory},
        return_app=True,
        app_token_env="",
    )
    assert app is not None

    response = TestClient(app).post("/test_agency/get_response", json={"message": "hello"})

    assert response.status_code == 200
    assert response.json()["response"] == "Test response"
    assert calls == ["preview", "request"]


def test_agui_attachment_only_file_ids_reaches_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_params: dict[str, Any] = {}

    async def fake_get_response_stream(self, message, **kwargs):
        captured_params["message"] = message
        captured_params["file_ids"] = kwargs["file_ids"]
        yield {"type": "text", "data": "Test"}

    monkeypatch.setattr(Agent, "get_response_stream", fake_get_response_stream)
    app = run_fastapi(
        agencies={"test_agency": _plain_agency},
        return_app=True,
        app_token_env="",
        enable_agui=True,
    )
    assert app is not None
    payload = {
        "thread_id": "test_thread",
        "run_id": "test_run",
        "state": None,
        "messages": [],
        "file_ids": ["file-123"],
        "tools": [],
        "context": [],
        "forwardedProps": None,
    }

    with TestClient(app).stream("POST", "/test_agency/get_response_stream", json=payload) as response:
        events = list(response.iter_lines())

    assert any("RUN_FINISHED" in event for event in events if event)
    assert captured_params == {"message": "", "file_ids": ["file-123"]}

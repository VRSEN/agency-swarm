from typing import Any

import pytest

CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
OPENAI_BASE_URL = "https://api.openai.com/v1"


def _preserved_message(origin: str, agent: str = "A") -> dict[str, Any]:
    return {
        "role": "system",
        "content": f"[{origin}] result",
        "message_origin": origin,
        "agent": agent,
        "callerAgent": None,
    }


def _regular_system_message(agent: str = "A") -> dict[str, Any]:
    return {
        "role": "system",
        "content": "regular system message",
        "message_origin": "other",
        "agent": agent,
        "callerAgent": None,
    }


def _roles(history: list[dict[str, Any]]) -> list[str]:
    return [item["role"] for item in history]


class _ThreadManager:
    def __init__(self, messages: list[dict[str, Any]] | None = None):
        self._messages = list(messages or [])

    def get_all_messages(self) -> list[dict[str, Any]]:
        return list(self._messages)

    def replace_messages(self, messages: list[dict[str, Any]]) -> None:
        self._messages = list(messages)


class _Response:
    final_output = "ok"


class _ResponseAgency:
    def __init__(
        self,
        messages: list[dict[str, Any]],
        loaded_history: list[dict[str, Any]],
        agents: dict[str, Any] | None = None,
        entry_points: list[Any] | None = None,
    ):
        self.agents = agents or {}
        if entry_points is not None:
            self.entry_points = entry_points
        self.thread_manager = _ThreadManager(messages)
        self._loaded_history = loaded_history

    async def get_response(self, **_kwargs) -> _Response:
        self._loaded_history[:] = self.thread_manager.get_all_messages()
        return _Response()


class _Model:
    model = "gpt-5.4-mini"

    def __init__(self, base_url: str):
        from openai import AsyncOpenAI

        self.openai_client = AsyncOpenAI(api_key="sk-agent", base_url=base_url)


class _AgentState:
    def __init__(self, name: str, base_url: str):
        self.name = name
        self.model = _Model(base_url)
        self.model_settings = None
        self._openai_client = None


async def _attach_noop(_agency) -> None:
    return None


def _patch_endpoint_setup(monkeypatch):
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)
    return endpoint_handlers


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("base_url", "expected_roles"),
    [
        (CODEX_BASE_URL, ["developer", "developer", "system"]),
        (OPENAI_BASE_URL, ["system", "system", "system"]),
    ],
)
async def test_response_endpoint_replays_preservation_roles_for_explicit_base_url(
    monkeypatch,
    base_url: str,
    expected_roles: list[str],
) -> None:
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    _patch_endpoint_setup(monkeypatch)
    replayed_history = [
        _preserved_message("web_search_preservation"),
        _preserved_message("file_search_preservation"),
        _regular_system_message(),
    ]
    loaded_history: list[dict[str, Any]] = []

    def _agency_factory(**kwargs):
        return _ResponseAgency(kwargs["load_threads_callback"](), loaded_history)

    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)
    response = await handler(
        BaseRequest(
            message="next",
            chat_history=replayed_history,
            client_config=ClientConfig(api_key="sk-request-key", base_url=base_url),
        ),
        token=None,
    )

    assert response["response"] == "ok"
    assert _roles(loaded_history) == expected_roles
    assert _roles(replayed_history) == ["system", "system", "system"]


@pytest.mark.asyncio
async def test_response_endpoint_rewrites_replay_for_inherited_default_codex_client(monkeypatch) -> None:
    pytest.importorskip("agents")

    from openai import AsyncOpenAI

    from agency_swarm.integrations.fastapi_utils import codex_replay
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest

    _patch_endpoint_setup(monkeypatch)
    monkeypatch.setattr(
        codex_replay,
        "get_default_openai_client",
        lambda: AsyncOpenAI(api_key="sk-default", base_url=CODEX_BASE_URL),
    )
    replayed_history = [_preserved_message("web_search_preservation"), _regular_system_message()]
    loaded_history: list[dict[str, Any]] = []

    def _agency_factory(**kwargs):
        return _ResponseAgency(kwargs["load_threads_callback"](), loaded_history)

    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)
    response = await handler(BaseRequest(message="next", chat_history=replayed_history), token=None)

    assert response["response"] == "ok"
    assert _roles(loaded_history) == ["developer", "system"]
    assert _roles(replayed_history) == ["system", "system"]


@pytest.mark.asyncio
async def test_response_endpoint_keeps_agent_non_codex_replay_when_default_is_codex(monkeypatch) -> None:
    pytest.importorskip("agents")

    from openai import AsyncOpenAI

    from agency_swarm.integrations.fastapi_utils import codex_replay
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest

    _patch_endpoint_setup(monkeypatch)
    monkeypatch.setattr(
        codex_replay,
        "get_default_openai_client",
        lambda: AsyncOpenAI(api_key="sk-default", base_url=CODEX_BASE_URL),
    )
    replayed_history = [_preserved_message("web_search_preservation")]
    loaded_history: list[dict[str, Any]] = []
    agents = {"A": _AgentState("A", OPENAI_BASE_URL)}

    def _agency_factory(**kwargs):
        return _ResponseAgency(kwargs["load_threads_callback"](), loaded_history, agents=agents)

    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)
    response = await handler(BaseRequest(message="next", chat_history=replayed_history), token=None)

    assert response["response"] == "ok"
    assert _roles(loaded_history) == ["system"]


@pytest.mark.asyncio
async def test_response_endpoint_rewrites_replay_for_agent_codex_client(monkeypatch) -> None:
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import codex_replay
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    _patch_endpoint_setup(monkeypatch)
    monkeypatch.setattr(codex_replay, "get_default_openai_client", lambda: None)
    replayed_history = [_preserved_message("file_search_preservation"), _regular_system_message()]
    loaded_history: list[dict[str, Any]] = []
    agents = {"A": _AgentState("A", CODEX_BASE_URL)}

    def _agency_factory(**kwargs):
        return _ResponseAgency(kwargs["load_threads_callback"](), loaded_history, agents=agents)

    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)
    response = await handler(
        BaseRequest(
            message="next",
            chat_history=replayed_history,
            client_config=ClientConfig(api_key="sk-request-key"),
        ),
        token=None,
    )

    assert response["response"] == "ok"
    assert _roles(loaded_history) == ["developer", "system"]
    assert _roles(replayed_history) == ["system", "system"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("recipient_agent", "expected_roles"),
    [
        ("OpenAI", ["system"]),
        (None, ["developer"]),
    ],
)
async def test_response_endpoint_uses_selected_or_default_agent_backend_in_mixed_agency(
    monkeypatch,
    recipient_agent: str | None,
    expected_roles: list[str],
) -> None:
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils import codex_replay
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    _patch_endpoint_setup(monkeypatch)
    monkeypatch.setattr(codex_replay, "get_default_openai_client", lambda: None)
    openai_agent = _AgentState("OpenAI", OPENAI_BASE_URL)
    codex_agent = _AgentState("Codex", CODEX_BASE_URL)
    agents = {"OpenAI": openai_agent, "Codex": codex_agent}
    replayed_history = [
        _preserved_message("web_search_preservation", agent=recipient_agent or "Codex"),
    ]
    loaded_history: list[dict[str, Any]] = []

    def _agency_factory(**kwargs):
        return _ResponseAgency(
            kwargs["load_threads_callback"](),
            loaded_history,
            agents=agents,
            entry_points=[codex_agent],
        )

    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)
    response = await handler(
        BaseRequest(
            message="next",
            recipient_agent=recipient_agent,
            chat_history=replayed_history,
            client_config=ClientConfig(api_key="sk-request-key"),
        ),
        token=None,
    )

    assert response["response"] == "ok"
    assert _roles(loaded_history) == expected_roles
    assert _roles(replayed_history) == ["system"]


@pytest.mark.asyncio
async def test_stream_endpoint_rewrites_codex_preservation_replay_without_mutating_input(monkeypatch) -> None:
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import ActiveRunRegistry, make_stream_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    _patch_endpoint_setup(monkeypatch)
    replayed_history = [
        _preserved_message("web_search_preservation"),
        _preserved_message("file_search_preservation"),
        _regular_system_message(),
    ]
    loaded_history: list[dict[str, Any]] = []

    class _HttpRequest:
        async def is_disconnected(self) -> bool:
            return False

    class _StreamAgency:
        def __init__(self, messages: list[dict[str, Any]]):
            self.agents = {}
            self.thread_manager = _ThreadManager(messages)

    def _agency_factory(**kwargs):
        loaded_history[:] = kwargs["load_threads_callback"]()
        return _StreamAgency(loaded_history)

    handler = make_stream_endpoint(
        BaseRequest,
        _agency_factory,
        verify_token=lambda: None,
        run_registry=ActiveRunRegistry(),
    )
    response = await handler(
        http_request=_HttpRequest(),
        request=BaseRequest(
            message="next",
            chat_history=replayed_history,
            client_config=ClientConfig(api_key="sk-request-key", base_url=CODEX_BASE_URL),
        ),
        token=None,
    )

    assert response.media_type == "text/event-stream"
    assert _roles(loaded_history) == ["developer", "developer", "system"]
    assert _roles(replayed_history) == ["system", "system", "system"]
    if response.background is not None:
        await response.background()


@pytest.mark.asyncio
async def test_agui_chat_endpoint_rewrites_codex_preservation_replay_without_mutating_input(monkeypatch) -> None:
    pytest.importorskip("agents")

    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_agui_chat_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig, RunAgentInputCustom

    _patch_endpoint_setup(monkeypatch)
    replayed_history = [
        _preserved_message("web_search_preservation"),
        _preserved_message("file_search_preservation"),
        _regular_system_message(),
    ]
    loaded_history: list[dict[str, Any]] = []

    class _AguiAgency:
        def __init__(self):
            self.agents = {}

    def _agency_factory(**kwargs):
        loaded_history[:] = kwargs["load_threads_callback"]()
        return _AguiAgency()

    handler = make_agui_chat_endpoint(RunAgentInputCustom, _agency_factory, verify_token=lambda: None)
    response = await handler(
        RunAgentInputCustom(
            thread_id="thread-1",
            run_id="run-1",
            state=None,
            messages=[],
            tools=[],
            context=[],
            forwarded_props=None,
            chat_history=replayed_history,
            client_config=ClientConfig(api_key="sk-request-key", base_url=CODEX_BASE_URL),
        ),
        token=None,
    )

    assert response.media_type == "text/event-stream"
    assert _roles(loaded_history) == ["developer", "developer", "system"]
    assert _roles(replayed_history) == ["system", "system", "system"]
    if response.background is not None:
        await response.background()

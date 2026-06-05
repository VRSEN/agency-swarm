from collections.abc import AsyncGenerator
from typing import Any, cast

import pytest
from openai import AsyncOpenAI

from agency_swarm import Agency, Agent
from agency_swarm.integrations.fastapi_utils.endpoint_handlers import (
    ActiveRunRegistry,
    make_agui_chat_endpoint,
    make_response_endpoint,
    make_stream_endpoint,
)
from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig, RunAgentInputCustom
from tests.deterministic_model import DeterministicModel
from tests.test_fastapi_utils_modules._codex_input_role_boundary_helpers import (
    CODEX_BASE_URL,
    OPENAI_BASE_URL,
    _agency_factory,
    _attach_noop,
    _filtered_roles,
    _history,
    _HttpRequest,
    _roles,
    _RunResult,
    _StreamedResult,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("base_url", "expected_model_roles"),
    [
        (CODEX_BASE_URL, ["developer", "developer", "developer", "user"]),
        (OPENAI_BASE_URL, ["system", "system", "system", "user"]),
    ],
)
async def test_response_endpoint_keeps_runner_input_and_filters_model_call_boundary(
    monkeypatch: pytest.MonkeyPatch,
    base_url: str,
    expected_model_roles: list[str],
) -> None:
    pytest.importorskip("agents")

    import agents

    captured: dict[str, Any] = {}

    async def _run(**kwargs: Any) -> _RunResult:
        captured["input"] = cast(list[dict[str, Any]], kwargs["input"])
        captured["run_config"] = kwargs["run_config"]
        captured["starting_agent"] = kwargs["starting_agent"]
        captured["model_roles"] = await _filtered_roles(
            kwargs["run_config"],
            kwargs["starting_agent"],
            captured["input"],
        )
        assert kwargs["starting_agent"].instructions == "normal agent instructions"
        return _RunResult()

    monkeypatch.setattr(agents.Runner, "run", _run)
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers", _attach_noop
    )

    replayed = _history()
    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)
    response = await handler(
        BaseRequest(
            message="next",
            chat_history=replayed,
            client_config=ClientConfig(api_key="sk-test", base_url=base_url),
        ),
        token=None,
    )

    assert response["response"] == "ok"
    assert _roles(captured["input"]) == ["system", "system", "system", "user"]
    assert captured["model_roles"] == expected_model_roles
    assert _roles(replayed) == ["system", "system", "system"]


@pytest.mark.asyncio
async def test_response_endpoint_keeps_system_replay_for_custom_model_with_codex_cached_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("agents")

    import agents

    captured: dict[str, Any] = {}

    async def _run(**kwargs: Any) -> _RunResult:
        starting_agent = kwargs["starting_agent"]
        captured["input"] = cast(list[dict[str, Any]], kwargs["input"])
        captured["run_config"] = kwargs["run_config"]
        captured["starting_agent"] = starting_agent
        captured["model_roles"] = await _filtered_roles(
            kwargs["run_config"],
            starting_agent,
            captured["input"],
        )
        assert starting_agent.model.model == "anthropic/claude-sonnet-4"
        assert str(starting_agent._openai_client.base_url).rstrip("/") == CODEX_BASE_URL
        return _RunResult()

    def _custom_model_agency_factory(**kwargs: Any) -> Agency:
        return Agency(
            Agent(
                name="A",
                instructions="normal agent instructions",
                model=DeterministicModel(model="anthropic/claude-sonnet-4"),
            ),
            load_threads_callback=kwargs["load_threads_callback"],
        )

    monkeypatch.setattr(agents.Runner, "run", _run)
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers", _attach_noop
    )

    replayed = _history()
    handler = make_response_endpoint(BaseRequest, _custom_model_agency_factory, verify_token=lambda: None)
    response = await handler(
        BaseRequest(
            message="next",
            chat_history=replayed,
            client_config=ClientConfig(api_key="sk-test", base_url=CODEX_BASE_URL),
        ),
        token=None,
    )

    assert response["response"] == "ok"
    assert _roles(captured["input"]) == ["system", "system", "system", "user"]
    assert captured["model_roles"] == ["system", "system", "system", "user"]
    assert _roles(replayed) == ["system", "system", "system"]


@pytest.mark.asyncio
async def test_stream_endpoint_keeps_runner_input_and_filters_model_call_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("agents")

    import agents

    captured: dict[str, Any] = {}

    def _run_streamed(**kwargs: Any) -> _StreamedResult:
        captured["input"] = cast(list[dict[str, Any]], kwargs["input"])
        captured["run_config"] = kwargs["run_config"]
        captured["starting_agent"] = kwargs["starting_agent"]
        assert kwargs["starting_agent"].instructions == "normal agent instructions"
        return _StreamedResult()

    monkeypatch.setattr(agents.Runner, "run_streamed", _run_streamed)
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers", _attach_noop
    )

    replayed = _history()
    handler = make_stream_endpoint(
        BaseRequest, _agency_factory, verify_token=lambda: None, run_registry=ActiveRunRegistry()
    )
    response = await handler(
        http_request=_HttpRequest(),
        request=BaseRequest(
            message="next",
            chat_history=replayed,
            client_config=ClientConfig(api_key="sk-test", base_url=CODEX_BASE_URL),
        ),
        token=None,
    )
    chunks = [chunk async for chunk in response.body_iterator]

    assert chunks[-1] == "event: end\ndata: [DONE]\n\n"
    assert _roles(captured["input"]) == ["system", "system", "system", "user"]
    assert captured["run_config"].call_model_input_filter is not None
    assert _roles(replayed) == ["system", "system", "system"]


@pytest.mark.asyncio
async def test_response_endpoint_rewrites_codex_system_replay_for_default_openai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("agents")

    import agents

    from agency_swarm.messages import codex_input

    captured: dict[str, Any] = {}

    async def _run(**kwargs: Any) -> _RunResult:
        captured["input"] = cast(list[dict[str, Any]], kwargs["input"])
        captured["run_config"] = kwargs["run_config"]
        captured["starting_agent"] = kwargs["starting_agent"]
        captured["model_roles"] = await _filtered_roles(
            kwargs["run_config"],
            kwargs["starting_agent"],
            captured["input"],
        )
        return _RunResult()

    monkeypatch.setattr(agents.Runner, "run", _run)
    monkeypatch.setattr(
        codex_input, "get_default_openai_client", lambda: AsyncOpenAI(api_key="sk-test", base_url=CODEX_BASE_URL)
    )
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers", _attach_noop
    )

    replayed = _history()
    handler = make_response_endpoint(BaseRequest, _agency_factory, verify_token=lambda: None)
    response = await handler(BaseRequest(message="next", chat_history=replayed), token=None)

    assert response["response"] == "ok"
    assert _roles(captured["input"]) == ["system", "system", "system", "user"]
    assert captured["model_roles"] == ["developer", "developer", "developer", "user"]


@pytest.mark.asyncio
async def test_agui_endpoint_keeps_runner_input_and_filters_model_call_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("agents")

    import agents

    captured: dict[str, Any] = {}

    def _run_streamed(**kwargs: Any) -> _StreamedResult:
        captured["input"] = cast(list[dict[str, Any]], kwargs["input"])
        captured["run_config"] = kwargs["run_config"]
        captured["starting_agent"] = kwargs["starting_agent"]
        assert kwargs["starting_agent"].instructions == "normal agent instructions"
        return _StreamedResult()

    monkeypatch.setattr(agents.Runner, "run_streamed", _run_streamed)
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers", _attach_noop
    )

    replayed = _history()
    handler = make_agui_chat_endpoint(RunAgentInputCustom, _agency_factory, verify_token=lambda: None)
    response = await handler(
        RunAgentInputCustom(
            thread_id="thread-1",
            run_id="run-1",
            state=None,
            messages=[{"id": "msg-1", "role": "user", "content": "next"}],
            tools=[],
            context=[],
            forwarded_props=None,
            chat_history=replayed,
            client_config=ClientConfig(api_key="sk-test", base_url=CODEX_BASE_URL),
        ),
        token=None,
    )
    chunks = [chunk async for chunk in response.body_iterator]

    assert chunks
    assert _roles(captured["input"]) == ["system", "system", "system", "user"]
    assert captured["run_config"].call_model_input_filter is not None
    assert _roles(replayed) == ["system", "system", "system"]


@pytest.mark.asyncio
async def test_generate_chat_name_rewrites_codex_system_input_before_direct_responses_create() -> None:
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers

    captured: dict[str, Any] = {}

    class _Event:
        def __init__(self, delta: str) -> None:
            self.type = "response.output_text.delta"
            self.delta = delta

    class _DummyResponse:
        def __aiter__(self) -> AsyncGenerator[_Event]:
            return self._events()

        async def _events(self) -> AsyncGenerator[_Event]:
            yield _Event("Replay")
            yield _Event(" Title")

    class _DummyResponses:
        async def create(self, **kwargs: Any) -> _DummyResponse:
            captured.update(kwargs)
            return _DummyResponse()

    class _DummyClient:
        base_url = CODEX_BASE_URL
        responses = _DummyResponses()

    result = await endpoint_handlers.generate_chat_name(
        [
            {"role": "system", "content": "replayed context", "agent": "A", "callerAgent": None},
            {"role": "user", "content": "next", "agent": "A", "callerAgent": None},
        ],
        openai_client=_DummyClient(),
    )

    assert result == "Replay Title"
    assert _roles(captured["input"]) == ["developer", "user"]

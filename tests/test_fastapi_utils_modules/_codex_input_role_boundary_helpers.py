import asyncio
from collections.abc import AsyncGenerator
from typing import Any, cast

from agents import ModelSettings, RunConfig, Tool
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff as SDKHandoff
from agents.items import ModelResponse, TResponseInputItem
from agents.models.interface import Model, ModelProvider
from agents.models.openai_responses import OpenAIResponsesModel
from agents.run_config import CallModelData, ModelInputData
from openai import AsyncOpenAI
from openai.types.responses.response_prompt_param import ResponsePromptParam

from agency_swarm import Agency, AgencyContext, Agent
from agency_swarm.agent.codex_model_input import with_codex_model_input_role_rewrite
from agency_swarm.messages import MessageFormatter
from agency_swarm.utils.thread import ThreadManager
from tests.deterministic_model import _build_message_response

CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
OPENAI_BASE_URL = "https://api.openai.com/v1"


class _HttpRequest:
    async def is_disconnected(self) -> bool:
        return False


class _RunResult:
    new_items: list[Any] = []
    final_output = "ok"


class _StreamedResult:
    final_output = "ok"
    new_items: list[Any] = []

    def stream_events(self) -> AsyncGenerator[dict[str, str]]:
        return _empty_stream()

    def cancel(self, *_args: Any, **_kwargs: Any) -> None:
        return None


async def _empty_stream() -> AsyncGenerator[dict[str, str]]:
    if False:
        yield {}


class _NonOpenAIProvider(ModelProvider):
    def get_model(self, model_name: str | None) -> Model:
        raise AssertionError(f"unexpected model lookup for {model_name}")


class _CapturingResponsesModel(OpenAIResponsesModel):
    def __init__(self, *, base_url: str) -> None:
        super().__init__(
            model="gpt-5.4-mini",
            openai_client=AsyncOpenAI(api_key="sk-test", base_url=base_url),
        )
        self.inputs: list[list[dict[str, Any]]] = []

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[SDKHandoff],
        tracing,
        previous_response_id: str | None = None,
        conversation_id: str | None = None,
        prompt: ResponsePromptParam | None = None,
    ) -> ModelResponse:
        if isinstance(input, list):
            self.inputs.append(cast(list[dict[str, Any]], input))
        return _build_message_response("worker done", str(self.model))


async def _attach_noop(_agency: Agency) -> None:
    return None


def _history() -> list[dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": "web results",
            "message_origin": "web_search_preservation",
            "agent": "A",
            "callerAgent": None,
            "timestamp": 1,
        },
        {
            "role": "system",
            "content": "file results",
            "message_origin": "file_search_preservation",
            "agent": "A",
            "callerAgent": None,
            "timestamp": 2,
        },
        {
            "role": "system",
            "content": "non-preservation replay",
            "message_origin": "other_replay",
            "agent": "A",
            "callerAgent": None,
            "timestamp": 3,
        },
    ]


def _roles(messages: list[dict[str, Any]]) -> list[str]:
    return [message["role"] for message in messages]


def _agency_factory(**kwargs: Any) -> Agency:
    return Agency(
        Agent(name="A", instructions="normal agent instructions"), load_threads_callback=kwargs["load_threads_callback"]
    )


async def _filtered_roles(
    run_config: RunConfig,
    agent: Agent,
    messages: list[dict[str, Any]],
) -> list[str]:
    model_data = ModelInputData(input=cast(list[TResponseInputItem], messages), instructions=None)
    filter_func = run_config.call_model_input_filter
    assert filter_func is not None
    filtered = await filter_func(CallModelData(model_data=model_data, agent=agent, context=None))
    return _roles(cast(list[dict[str, Any]], filtered.input))


def _model_call_roles(agent: Agent, run_config: RunConfig | None) -> list[str]:
    replayed = _history()
    thread_manager = ThreadManager()
    thread_manager._store.messages = replayed
    context = AgencyContext(agency_instance=None, thread_manager=thread_manager)

    history = cast(
        list[dict[str, Any]],
        MessageFormatter.prepare_history_for_runner(
            [{"role": "user", "content": "next"}],
            agent,
            None,
            context,
            run_config_override=run_config,
        ),
    )

    assert _roles(replayed[:3]) == ["system", "system", "system"]
    assert _roles(history) == ["system", "system", "system", "user"]
    wrapped = with_codex_model_input_role_rewrite(run_config or RunConfig())
    return asyncio.run(_filtered_roles(wrapped, agent, history))

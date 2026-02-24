"""Regression coverage for LiteLLM-to-Responses history replay."""

from __future__ import annotations

import copy
import importlib
import os

import pytest
from agents import ModelSettings

from agency_swarm import Agency, Agent, function_tool

pytest.importorskip("litellm")
LitellmModel = importlib.import_module("agents.extensions.models.litellm_model").LitellmModel

pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY is required for LiteLLM/OpenAI integration test.",
)


@function_tool
def get_user_id(args: str) -> str:
    """Returns a deterministic user ID for replay tests."""
    return "User id is 1245725189"


def _build_agent(*, model: str | LitellmModel) -> Agent:
    return Agent(
        name="SwitchAgent",
        instructions=(
            "Always call the get_user_id tool exactly once before giving your final answer. "
            "Return a short answer that includes the tool result."
        ),
        model_settings=ModelSettings(tool_choice="required"),
        model=model,
        tools=[get_user_id],
    )


def test_litellm_history_replays_into_openai_responses_provider() -> None:
    litellm_agency = Agency(
        _build_agent(model=LitellmModel(model="openai/gpt-5-mini", api_key=os.getenv("OPENAI_API_KEY")))
    )
    litellm_agency.get_response_sync(message="Find my user id.")

    persisted_history = copy.deepcopy(litellm_agency.thread_manager.get_all_messages())
    assert any(msg.get("type") == "function_call" for msg in persisted_history), (
        "Expected LiteLLM history to include at least one function_call item."
    )
    assert any(msg.get("type") == "function_call_output" for msg in persisted_history), (
        "Expected LiteLLM history to include at least one function_call_output item."
    )
    assert any(
        msg.get("type") == "function_call" and isinstance(msg.get("id"), str) and msg.get("id") == msg.get("call_id")
        for msg in persisted_history
    ), "Expected LiteLLM function_call items to persist replay IDs as id == call_id."

    responses_agency = Agency(
        _build_agent(model="gpt-5-mini"),
        load_threads_callback=lambda: copy.deepcopy(persisted_history),
    )
    responses_agency.get_response_sync(message="Use the tool again and report my id.")

    replayed_history = responses_agency.thread_manager.get_all_messages()
    assert len(replayed_history) > len(persisted_history), (
        "Expected second run to append new messages after loading persisted LiteLLM history."
    )
    assert any(msg.get("type") == "function_call" for msg in replayed_history[len(persisted_history) :]), (
        "Expected OpenAI Responses turn to execute at least one new function_call."
    )


@pytest.mark.asyncio
async def test_litellm_stream_history_replays_into_openai_responses_provider() -> None:
    litellm_agency = Agency(
        _build_agent(model=LitellmModel(model="openai/gpt-5-mini", api_key=os.getenv("OPENAI_API_KEY")))
    )
    stream = litellm_agency.get_response_stream(message="Find my user id.")
    async for _ in stream:
        pass
    final_result = await stream.wait_final_result()
    assert final_result is not None, "Expected streaming run to produce a final result."

    persisted_history = copy.deepcopy(litellm_agency.thread_manager.get_all_messages())
    assert any(
        msg.get("type") == "function_call" and isinstance(msg.get("id"), str) and msg.get("id") == msg.get("call_id")
        for msg in persisted_history
    ), "Expected streamed LiteLLM function_call items to persist replay IDs as id == call_id."

    responses_agency = Agency(
        _build_agent(model="gpt-5-mini"),
        load_threads_callback=lambda: copy.deepcopy(persisted_history),
    )
    await responses_agency.get_response(message="Use the tool again and report my id.")

    replayed_history = responses_agency.thread_manager.get_all_messages()
    assert len(replayed_history) > len(persisted_history), (
        "Expected second run to append new messages after loading streamed LiteLLM history."
    )
    assert any(msg.get("type") == "function_call" for msg in replayed_history[len(persisted_history) :]), (
        "Expected OpenAI Responses turn to execute at least one new function_call after streaming replay."
    )

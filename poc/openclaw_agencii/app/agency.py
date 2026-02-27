from __future__ import annotations

import os

from agents import OpenAIResponsesModel
from openai import AsyncOpenAI

from agency_swarm import Agency, Agent


def _default_proxy_base_url() -> str:
    port = os.getenv("PORT", "8080")
    return f"http://127.0.0.1:{port}/openclaw/v1"


def _build_openclaw_model() -> OpenAIResponsesModel:
    base_url = os.getenv("OPENCLAW_PROXY_BASE_URL", _default_proxy_base_url())
    api_key = os.getenv("OPENCLAW_PROXY_API_KEY", "sk-openclaw-proxy")
    model_name = os.getenv("OPENCLAW_AGENT_MODEL", "openclaw:main")

    return OpenAIResponsesModel(
        model=model_name,
        openai_client=AsyncOpenAI(base_url=base_url, api_key=api_key),
    )


def create_agency(load_threads_callback=None):
    """Create a PoC agency where one specialist is OpenClaw-backed."""
    openclaw_specialist = Agent(
        name="OpenClawSpecialist",
        description="Delegates execution to OpenClaw through OpenResponses API.",
        instructions=(
            "You are an external-agent bridge specialist. Focus on tool-use heavy subtasks, "
            "and return concise actionable outputs for the coordinator."
        ),
        model=_build_openclaw_model(),
    )

    coordinator = Agent(
        name="Coordinator",
        description="Coordinates work and delegates subtasks to OpenClawSpecialist when needed.",
        instructions=(
            "You coordinate user requests. Delegate implementation-heavy subtasks to "
            "OpenClawSpecialist via send_message when that improves task quality."
        ),
        model=_build_openclaw_model(),
    )

    return Agency(
        coordinator,
        openclaw_specialist,
        communication_flows=[coordinator > openclaw_specialist],
        name="openclaw-agencii-poc",
        shared_instructions=(
            "This PoC validates OpenClaw interoperability via OpenResponses while preserving "
            "Agency Swarm communication and streaming semantics."
        ),
        load_threads_callback=load_threads_callback,
    )

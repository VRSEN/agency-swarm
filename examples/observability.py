"""Observability demo showing OpenAI tracing plus optional Langfuse and AgentOps tracing.

Make sure you have correct environment variables set up prior to running the script
for any optional tracking providers you want to enable.

OpenAI does not require extra setup, results can be found here: https://platform.openai.com/traces

For Langfuse and AgentOps, follow the setup guides below.
Langfuse setup guide: https://langfuse.com/integrations/model-providers/openai-py
AgentOps setup guide: https://docs.agentops.ai/v2/integrations/openai_agents_python

Results can be found in the platform's respective dashboards.

Run with: python examples/observability.py
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from statistics import mean, stdev
from typing import Any

# Path setup for standalone examples
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

try:  # noqa: E402
    import agentops  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised by example smoke test
    agentops = None

try:  # noqa: E402
    from langfuse import observe  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised by example smoke test

    def observe(*_args, **_kwargs):
        def decorator(func):
            return func

        return decorator

    _LANGFUSE_AVAILABLE = False
else:
    _LANGFUSE_AVAILABLE = True

from agency_swarm import (  # noqa: E402
    Agency,
    Agent,
    RunContextWrapper,
    function_tool,
    trace,
)

logging.basicConfig(level=logging.INFO)


@dataclass(frozen=True)
class TracingProof:
    """Output captured from a tracing run for release-test assertions."""

    final_output: str
    function_outputs: list[str]


# ────────────────────────────────
# Tool definition
# ────────────────────────────────


@function_tool
async def analyze_dataset(ctx: RunContextWrapper[Any], dataset: list[int]) -> str:
    """Analyze a dataset and return basic statistics."""
    print(f"DATASET ANALYZED by {ctx.context.current_agent_name}: {dataset}")
    return f"Mean: {mean(dataset):.1f}, Standard Deviation: {stdev(dataset):.1f}"


# ────────────────────────────────
# Agency definition (agents + flows)
# ────────────────────────────────


def create_agency() -> Agency:
    """Create agency with CEO, Developer, and Analyst."""
    ceo = Agent(
        name="CEO",
        instructions="You are the CEO. NEVER execute tasks yourself. Instead, DELEGATE all tasks: coding tasks to Developer and data analysis to DataAnalyst.",
        description="Manages projects and coordinates between team members",
        model="gpt-5.4-mini",
    )

    developer = Agent(
        name="Developer",
        instructions="You are the Developer. Solve coding problems by implementing solutions and writing code.",
        description="Implements technical solutions and writes code",
        model="gpt-5.4-mini",
    )

    analyst = Agent(
        name="DataAnalyst",
        instructions="You are the Data Analyst. Analyze data and provide insights. Always use analyze_dataset in your response to process the dataset.",
        description="Analyzes data and provides insights",
        model="gpt-5.4-mini",
        tools=[analyze_dataset],
    )

    return Agency(
        ceo,
        communication_flows=[
            ceo > developer,
            ceo > analyst,
        ],
    )


# ────────────────────────────────
# Example tracing wrappers
# ────────────────────────────────
async def openai_tracing(input_message: str) -> TracingProof:
    agency_instance = create_agency()
    with trace("OpenAI tracing"):
        response = await agency_instance.get_response(message=input_message)
    return TracingProof(response.final_output, _function_outputs(agency_instance))


@observe()
async def langfuse_tracing(input_message: str) -> TracingProof:
    if not _LANGFUSE_AVAILABLE:
        raise ModuleNotFoundError("langfuse is not installed")
    if os.getenv("LANGFUSE_SECRET_KEY") is None or os.getenv("LANGFUSE_PUBLIC_KEY") is None:
        raise ValueError("LANGFUSE api keys are not set")

    agency_instance = create_agency()

    @observe()
    async def get_response_wrapper(message: str) -> Any:
        return await agency_instance.get_response(
            message=message,
        )

    response = await get_response_wrapper(input_message)
    return TracingProof(response.final_output, _function_outputs(agency_instance))


async def agentops_tracing(input_message: str) -> TracingProof:
    if agentops is None:
        raise ModuleNotFoundError("agentops is not installed")
    if os.getenv("AGENTOPS_API_KEY") is None:
        raise ValueError("AGENTOPS_API_KEY is not set")
    agentops.init(auto_start_session=True, trace_name="Agentops tracing", tags=["openai", "agentops-example"])
    tracer = agentops.start_trace(trace_name="Agentops tracing", tags=["openai", "agentops-example"])

    agency_instance = create_agency()
    response = await agency_instance.get_response(
        message=input_message,
    )
    agentops.end_trace(tracer, end_state="Success")
    return TracingProof(response.final_output, _function_outputs(agency_instance))


def _function_outputs(agency: Agency) -> list[str]:
    """Return persisted function outputs from the last agency run."""
    outputs: list[str] = []
    for message in agency.thread_manager.get_all_messages():
        if not isinstance(message, dict) or message.get("type") != "function_call_output":
            continue
        outputs.append(str(message.get("output", "")))
    return outputs


def _require_text(haystack: str, needles: list[str], proof_name: str) -> None:
    missing = [needle for needle in needles if needle not in haystack]
    if missing:
        raise RuntimeError(f"{proof_name} did not return required evidence: {missing}")


def _require_tracing_proof(provider: str, proof: TracingProof) -> None:
    if not proof.final_output.strip():
        raise RuntimeError(f"{provider} tracing returned an empty response")
    proof_text = "\n".join([proof.final_output, *proof.function_outputs])
    _require_text(proof.final_output.lower(), ["factorial"], f"{provider} tracing")
    _require_text(proof_text, ["Mean: 20.0", "Standard Deviation: 7.9"], f"{provider} tracing")


def _missing_env_vars(*names: str) -> list[str]:
    return [name for name in names if not os.getenv(name)]


def _print_result(provider: str, proof: TracingProof) -> None:
    _require_tracing_proof(provider, proof)
    print(proof.final_output)
    print(f"{provider} tracing proof completed with factorial and dataset evidence.")


async def main() -> None:
    test_message = "Create a function to calculate factorial and analyze the dataset [10, 25, 15, 30, 20]."

    print("Running OpenAI tracing...")
    _print_result("OpenAI", await openai_tracing(test_message))

    print("\nRunning Langfuse tracing...")
    missing_langfuse = _missing_env_vars("LANGFUSE_SECRET_KEY", "LANGFUSE_PUBLIC_KEY")
    if not _LANGFUSE_AVAILABLE:
        print("SKIPPED: langfuse is not installed.")
    elif missing_langfuse:
        print(f"SKIPPED: missing {', '.join(missing_langfuse)}.")
    else:
        _print_result("Langfuse", await langfuse_tracing(test_message))

    print("\nRunning AgentOps tracing...")
    missing_agentops = _missing_env_vars("AGENTOPS_API_KEY")
    if agentops is None:
        print("SKIPPED: agentops is not installed.")
    elif missing_agentops:
        print(f"SKIPPED: missing {', '.join(missing_agentops)}.")
    else:
        _print_result("AgentOps", await agentops_tracing(test_message))


# ────────────────────────────────
# Entry point
# ────────────────────────────────
if __name__ == "__main__":
    asyncio.run(main())

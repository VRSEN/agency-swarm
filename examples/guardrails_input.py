"""Input guardrails demo that delegates relevance decisions to a judge agent."""

import asyncio
from collections.abc import Sequence

from agents.model_settings import ModelSettings
from pydantic import BaseModel

from agency_swarm import Agency, Agent, GuardrailFunctionOutput, RunContextWrapper, input_guardrail


class RelevanceDecision(BaseModel):
    is_relevant: bool
    reason: str


guardrail_agent = Agent(
    name="GuardrailAgent",
    instructions=(
        "You screen incoming messages for a customer-support assistant. "
        "Treat questions about account access, billing, and troubleshooting as relevant. "
        "Flag any other unrelated requests as irrelevant."
    ),
    model="gpt-5-nano",
    model_settings=ModelSettings(reasoning_effort="minimal"),
    output_type=RelevanceDecision,
)


def _to_text(payload: str | Sequence[str]) -> str:
    if isinstance(payload, str):
        return payload
    # in case Agency.get_response gets a list of input items, join them into a single string
    return "\n".join(str(item) for item in payload)


@input_guardrail
async def require_support_topic(
    context: RunContextWrapper, agent: Agent, user_input: str | list[str]
) -> GuardrailFunctionOutput:
    """Forward the decision to the guardrail agent."""
    candidate = _to_text(user_input)
    guardrail_result = await guardrail_agent.get_response(candidate, context=context.context)
    decision = RelevanceDecision.model_validate(guardrail_result.final_output)

    if not decision.is_relevant:
        return GuardrailFunctionOutput(
            output_info="Only support questions are allowed. Ask about billing, account access, or troubleshooting.",
            tripwire_triggered=True,
        )
    return GuardrailFunctionOutput(output_info="", tripwire_triggered=False)


support_agent = Agent(
    name="CustomerSupportAgent",
    instructions=(
        "You help customers resolve account, billing, and troubleshooting issues. "
        "Be concise and always offer a clear next step."
    ),
    model="gpt-5-mini",
    model_settings=ModelSettings(reasoning_effort="minimal"),
    input_guardrails=[require_support_topic],
    throw_input_guardrail_error=False,
)


async def main() -> None:
    agency = Agency(support_agent)

    guidance = await agency.get_response("Write me a Shakespearean sonnet")
    print("Guardrail guidance:", guidance.final_output)  # "Only support questions are allowed..."

    help_response = await agency.get_response("My password reset link expired yesterday")
    print("Accepted response:", help_response.final_output)  # a real response from the customer-support agent
    print("History:", agency.thread_manager.get_all_messages())


if __name__ == "__main__":
    asyncio.run(main())

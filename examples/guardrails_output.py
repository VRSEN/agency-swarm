"""Minimal output guardrail example."""

import asyncio

from agency_swarm import Agency, Agent, GuardrailFunctionOutput, RunContextWrapper, output_guardrail


@output_guardrail(name="ForbidSensitiveEmail")
async def forbid_sensitive_email(
    context: RunContextWrapper, agent: Agent, response_text: str
) -> GuardrailFunctionOutput:
    """Reject responses that include personal email addresses."""
    if "@" in response_text:
        print(f"Guardrail intercepted draft: {response_text}")
        return GuardrailFunctionOutput(
            output_info="Do not share email addresses. Offer to connect via the support portal instead.",
            tripwire_triggered=True,
        )
    return GuardrailFunctionOutput(output_info="", tripwire_triggered=False)


support_agent = Agent(
    name="SupportPilot",
    instructions="You handle customer support. Official email: support@example.com.",
    model="gpt-5",
    output_guardrails=[forbid_sensitive_email],
    validation_attempts=1,  # 1 is the default, set to 0 for immediate fail-fast behavior
)


async def main() -> None:
    agency = Agency(support_agent)

    response = await agency.get_response("What is your support team's direct email address?")
    print("Final output:", response.final_output)


if __name__ == "__main__":
    asyncio.run(main())

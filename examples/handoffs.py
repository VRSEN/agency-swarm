"""
Handoffs Example

This example demonstrates a realistic handoff workflow using SendMessageHandoff.

- DevLead implements features and hands off security-sensitive work to SecurityEngineer (default reminder)
- SecurityEngineer performs audits and hands off to ComplianceOfficer (reminder disabled)
- ComplianceOfficer completes compliance checks and hands back to DevLead, triggering a custom reminder for DevLead

Run with: python examples/handoffs.py

Try: "Implement user authentication with 2FA and ensure it passes security and compliance."
"""

import asyncio
import logging
import os
import sys

from utils import print_history

# Path setup so the example can be run standalone
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agency_swarm import Agency, Agent, ModelSettings, function_tool
from agency_swarm.tools.send_message import SendMessageHandoff

# Setup logging
logging.basicConfig(level=logging.WARNING)
logging.getLogger("agency_swarm").setLevel(
    logging.DEBUG if os.getenv("DEBUG_LOGS", "False").lower() == "true" else logging.WARNING
)


@function_tool
def implement_feature(feature_name: str) -> str:
    """Implement a feature with basic scaffolding and docs."""
    return (
        f"Feature '{feature_name}' implemented with auth middleware, input validation, and error handling. "
        "Added developer docs and unit tests."
    )


@function_tool
def security_audit(component: str) -> str:
    """Perform a targeted security audit of the given component."""
    return f"Security audit for {component}: No critical findings. 1 medium (sanitize inputs), 1 low (log rotation)."


@function_tool
def vulnerability_scan(target: str) -> str:
    """Scan the target for known vulnerabilities and CVEs."""
    return f"Scan for {target}: 0 critical CVEs, 1 medium (dependency), 2 low (headers)."


@function_tool
def policy_check(area: str) -> str:
    """Check policy adherence for a given domain (e.g., auth, data retention)."""
    return f"Policy check for {area}: Meets GDPR data minimization; add DPA reference in docs."


@function_tool
def generate_compliance_report(scope: str) -> str:
    """Generate a compliance report for audit trail and sign-off."""
    return f"Compliance report generated for {scope}: Ready for sign-off; attach to release notes."


# By default, to reduce hallucinations, when using SendMessageHandoff, a reminder system message is added to the history.
# You can adjust the reminder message per receiving agent via `Agent.handoff_reminder` or disable it entirely by subclassing.
class NoReminderHandoff(SendMessageHandoff):
    """SendMessageHandoff with no reminder."""

    add_reminder = False  # True by default


dev_lead = Agent(
    name="DevLead",
    description="Leads development, implements features, and delegates security and compliance tasks.",
    instructions=(
        "You are the DevLead. Implement requested features using tools and provide technical context. "
        "When the task involves security concerns, hand off to SecurityEngineer using the transfer tool. "
        "Include all relevant details and acceptance criteria in the handoff message. "
        "Only use transfer tool once."
    ),
    tools=[implement_feature],
    # Reminder shown when DevLead receives a handoff (e.g., from ComplianceOfficer).
    # Default format: "Transfer completed. You are {recipient_agent_name}. Please continue the task."
    handoff_reminder="Compliance review is complete. Confirm deployment steps and attach audit artifacts.",
    model_settings=ModelSettings(temperature=0.0),
)

security_engineer = Agent(
    name="SecurityEngineer",
    description="Performs security audits and vulnerability assessments prior to release.",
    instructions=(
        "You are the SecurityEngineer. Perform audits and scans using your tools. "
        "Include full tool outputs verbatim. When compliance review is required, hand off to ComplianceOfficer "
        "without adding a reminder (disabled)."
    ),
    tools=[security_audit, vulnerability_scan],
    model_settings=ModelSettings(temperature=0.0),
)

compliance_officer = Agent(
    name="ComplianceOfficer",
    description="Verifies regulatory and policy compliance and issues sign-off.",
    instructions=(
        "You are the ComplianceOfficer. Run policy checks and generate compliance reports. "
        "When handing back to DevLead, confirm sign-off steps and artifacts—they receive a custom reminder to double-check."
    ),
    tools=[policy_check, generate_compliance_report],
    model_settings=ModelSettings(temperature=0.0),
)

agency = Agency(
    dev_lead,
    communication_flows=[
        (dev_lead > security_engineer, SendMessageHandoff),
        (security_engineer > compliance_officer, NoReminderHandoff),
        (compliance_officer > dev_lead, SendMessageHandoff),
    ],
    shared_instructions=(
        "Deliver secure, compliant features. Preserve exact tool outputs in responses and include sign-off details."
    ),
)


async def main(input_message):
    async for _ in agency.get_response_stream(input_message):
        pass
    return


if __name__ == "__main__":
    input_message = (
        "Implement user authentication with 2FA for our web app. "
        "After implementation, hand off to SecurityEngineer to run security_audit on the auth module and vulnerability_scan on the web app. "
        "Then hand off to ComplianceOfficer to run policy_check on authentication and generate_compliance_report for release v1.2. "
        "Finally, hand back to DevLead to confirm deployment sign-off steps and attach the compliance report."
    )

    asyncio.run(main(input_message))
    print_history(agency.thread_manager, roles=("assistant", "system", "function_call", "function_call_output"))

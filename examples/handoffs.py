"""
Handoffs Example

This example demonstrates a realistic handoff workflow using Handoff.

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

# Path setup so the example can be run standalone
examples_root = os.path.abspath(os.path.dirname(__file__))
repo_root = os.path.abspath(os.path.join(examples_root, ".."))
sys.path.insert(0, os.path.join(repo_root, "src"))
sys.path.insert(0, examples_root)

from utils import print_history  # noqa: E402

from agency_swarm import Agency, Agent, ModelSettings, function_tool  # noqa: E402
from agency_swarm.tools.send_message import Handoff  # noqa: E402

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


# By default, to reduce hallucinations, when using Handoff, a reminder system message is added to the history.
# You can adjust the reminder message per receiving agent via `Agent.handoff_reminder` or disable it entirely by subclassing.
class NoReminderHandoff(Handoff):
    """Handoff with no reminder."""

    add_reminder = False  # True by default


dev_lead = Agent(
    name="DevLead",
    description="Leads development, implements features, and delegates security and compliance tasks.",
    instructions=(
        "You are the DevLead. Implement requested features using tools and provide technical context. "
        "When the task involves security concerns, call implement_feature, then immediately use "
        "transfer_to_SecurityEngineer. Do not stop after implementation. "
        "Include all relevant details and acceptance criteria in the handoff message. "
        "Only use transfer_to_SecurityEngineer once."
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
        "For this workflow, call security_audit and vulnerability_scan, include both tool outputs verbatim, "
        "then immediately use transfer_to_ComplianceOfficer. Do not stop after security outputs. "
        "The transfer to ComplianceOfficer has no reminder."
    ),
    tools=[security_audit, vulnerability_scan],
    model_settings=ModelSettings(temperature=0.0),
)

compliance_officer = Agent(
    name="ComplianceOfficer",
    description="Verifies regulatory and policy compliance and issues sign-off.",
    instructions=(
        "You are the ComplianceOfficer. Run policy checks and generate compliance reports. "
        "For this workflow, call policy_check and generate_compliance_report, include both tool outputs verbatim, "
        "then immediately use transfer_to_DevLead with sign-off steps and artifacts. "
        "Do not stop before handing back to DevLead."
    ),
    tools=[policy_check, generate_compliance_report],
    model_settings=ModelSettings(temperature=0.0),
)

agency = Agency(
    dev_lead,
    communication_flows=[
        (dev_lead > security_engineer, Handoff),
        (security_engineer > compliance_officer, NoReminderHandoff),
        (compliance_officer > dev_lead, Handoff),
    ],
    shared_instructions=(
        "Deliver secure, compliant features. Preserve exact tool outputs in responses and include sign-off details."
    ),
)


def assert_semantic_success() -> None:
    """Require the full handoff chain and compliance sign-off tool outputs."""
    messages = agency.thread_manager.get_all_messages()
    function_calls = _function_calls()
    tool_outputs = "\n".join(
        str(message.get("output", ""))
        for message in messages
        if isinstance(message, dict) and message.get("type") == "function_call_output"
    )

    required_calls = {
        "implement_feature",
        "security_audit",
        "vulnerability_scan",
        "policy_check",
        "generate_compliance_report",
        "transfer_to_SecurityEngineer",
        "transfer_to_ComplianceOfficer",
        "transfer_to_DevLead",
    }
    missing_calls = sorted(required_calls - function_calls)
    if missing_calls:
        raise RuntimeError(f"Missing expected workflow calls: {missing_calls}")

    required_outputs = [
        "Security audit for auth module",
        "Scan for web app",
        "Policy check for authentication",
        "Compliance report generated for release v1.2",
    ]
    missing_outputs = [expected for expected in required_outputs if expected not in tool_outputs]
    if missing_outputs:
        raise RuntimeError(f"Missing expected workflow outputs: {missing_outputs}")

    print("\nSemantic check passed: security, compliance, and DevLead sign-off handoffs completed.")


def _function_calls() -> set[str]:
    return {
        str(message.get("name"))
        for message in agency.thread_manager.get_all_messages()
        if isinstance(message, dict) and message.get("type") == "function_call"
    }


def _has_calls(*names: str) -> bool:
    function_calls = _function_calls()
    return all(name in function_calls for name in names)


async def _run_message(message: str, *, recipient_agent: Agent | None = None) -> None:
    async for _ in agency.get_response_stream(message, recipient_agent=recipient_agent):
        pass


async def main(input_message):
    await _run_message(input_message)
    if not _has_calls("policy_check", "generate_compliance_report", "transfer_to_ComplianceOfficer"):
        await _run_message(
            "Run security_audit on the auth module and vulnerability_scan on the web app. "
            "Then use transfer_to_ComplianceOfficer so ComplianceOfficer runs policy_check on authentication "
            "and generate_compliance_report for release v1.2.",
            recipient_agent=security_engineer,
        )
    if not _has_calls("transfer_to_DevLead"):
        await _run_message(
            "Run policy_check on authentication and generate_compliance_report for release v1.2. "
            "Then use transfer_to_DevLead with deployment sign-off steps and attach the compliance report.",
            recipient_agent=compliance_officer,
        )
    assert_semantic_success()
    return


if __name__ == "__main__":
    input_message = (
        "Implement user authentication with 2FA for our web app. "
        "After implementation, hand off to SecurityEngineer to run security_audit on the auth module and vulnerability_scan on the web app. "
        "Then hand off to ComplianceOfficer to run policy_check on authentication and generate_compliance_report for release v1.2. "
        "Finally, hand back to DevLead with transfer_to_DevLead to confirm deployment sign-off steps and attach the compliance report. "
        "Use the exact transfer tools: transfer_to_SecurityEngineer, transfer_to_ComplianceOfficer, and transfer_to_DevLead."
    )

    asyncio.run(main(input_message))
    print_history(agency.thread_manager, roles=("assistant", "system", "function_call", "function_call_output"))

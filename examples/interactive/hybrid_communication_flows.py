"""
Hybrid Communication Flows Example

This example demonstrates advanced communication patterns in Agency Swarm by combining
two different communication mechanisms: SendMessage tools and handoffs.

## Agents and Their Roles

- **ProjectManager**: Coordinates projects using custom context-aware messaging
- **Developer**: Implements features and transfers to security expert when needed
- **SecurityExpert**: Performs security audits and vulnerability assessments

## Communication Flow

The agency demonstrates a real-world software development workflow:
1. ProjectManager delegates tasks with project context and priority
2. Developer implements features and reviews code quality
3. Developer can transfer to SecurityExpert for security-sensitive work
4. SecurityExpert performs audits and returns findings

## Usage

Run this example with: python examples/hybrid_communication_flows.py

It will open the TUI for the agency, where you can interact with the agency.
Ask ProjectManager to implement a new feature with code quality review and security audit.
For example, you can use the following input query:
'''
We need to implement a user authentication system for our web application.
This is a high priority item for our security review phase.
Please implement the feature and ensure it meets security standards.
'''
"""

import asyncio
import logging
import os
import sys

# Path setup so the example can be run standalone
examples_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
repo_root = os.path.abspath(os.path.join(examples_root, ".."))
sys.path.insert(0, os.path.join(repo_root, "src"))
sys.path.insert(0, repo_root)

from pydantic import Field  # noqa: E402

from agency_swarm import Agency, Agent, ModelSettings, function_tool  # noqa: E402
from agency_swarm.tools.send_message import Handoff, SendMessage  # noqa: E402

# Setup logging
logging.basicConfig(level=logging.WARNING)
logging.getLogger("agency_swarm").setLevel(
    logging.DEBUG if os.getenv("DEBUG_LOGS", "False").lower() == "true" else logging.WARNING
)


# Define tools for the agents
@function_tool
def review_code_quality(code_snippet: str) -> str:
    """Review code for quality, best practices, and potential improvements."""
    return f"Code quality review complete for {len(code_snippet)} characters. Found 2 minor improvements: variable naming and error handling."


@function_tool
def implement_feature(feature_name: str) -> str:
    """Implement a software feature with basic structure."""
    return f"Feature '{feature_name}' implemented with authentication middleware, input validation, and error handling."


@function_tool
def security_audit(component: str) -> str:
    """Perform comprehensive security audit of a component."""
    return f"Security audit complete for {component}. Found: 1 SQL injection vulnerability, 2 XSS risks, authentication bypass potential. Recommendations provided."


@function_tool
def vulnerability_scan(target: str) -> str:
    """Scan for known vulnerabilities and security weaknesses."""
    return f"Vulnerability scan of {target} complete. Detected 3 medium-risk issues: outdated dependencies, weak encryption, missing rate limiting."


# Custom SendMessage that adds project context
class SendMessageWithProjectContext(SendMessage):
    """SendMessage with project context tracking."""

    tool_name = "send_message_with_context"

    project_phase: str = Field(
        description=(
            "Current phase of the project (planning, development, testing, security_review, deployment). "
            "This helps the recipient understand the urgency and focus area for their response."
        )
    )
    priority_level: str = Field(
        description=(
            "Priority level of this task. Critical items need immediate attention, "
            "high priority items should be completed within the day."
        )
    )


project_manager = Agent(
    name="ProjectManager",
    description="Coordinates software development projects and ensures quality delivery",
    instructions=(
        "You are a Project Manager responsible for coordinating software development projects. "
        "Your role is to delegate tasks, track progress, and ensure deliverables meet requirements. "
        "When delegating work, always specify the project phase and priority level. "
        "CRITICAL: When you receive responses from team members, include their complete "
        "findings and recommendations in your final output to maintain transparency."
    ),
    model_settings=ModelSettings(temperature=0),
)

developer = Agent(
    name="Developer",
    description="Software developer who implements features and coordinates with security experts",
    instructions=(
        "You are a Senior Developer responsible for implementing software features. "
        "You have access to code quality review and feature implementation tools. "
        "For security-sensitive features, call implement_feature and review_code_quality, then immediately use "
        "transfer_to_SecurityExpert. Do not stop after implementation or code review. "
        "Always provide detailed technical responses including any tool outputs. "
        "When performing handoffs, transfer complete context including all technical details."
    ),
    tools=[review_code_quality, implement_feature],
    model_settings=ModelSettings(temperature=0),
)

security_expert = Agent(
    name="SecurityExpert",
    description="Security specialist who performs audits and vulnerability assessments",
    instructions=(
        "You are a Security Expert specializing in application security audits. "
        "You have access to security audit and vulnerability scanning tools. "
        "For this workflow, always call security_audit and vulnerability_scan. "
        "Include both complete tool outputs in your response. "
        "Provide comprehensive security assessments with specific recommendations. "
        "Focus on practical, actionable security improvements."
    ),
    tools=[security_audit, vulnerability_scan],
    model_settings=ModelSettings(temperature=0),
)

agency = Agency(
    project_manager,
    communication_flows=[
        (project_manager > developer, SendMessageWithProjectContext),
        (developer > security_expert, Handoff),
    ],
    shared_instructions="Focus on delivering secure, high-quality software. Use project context to prioritize work.",
)


DEMO_PROMPT = """We need to implement a user authentication system for our web application.
This is a high priority item for our security review phase.
Please implement the feature, run code quality review, and transfer to SecurityExpert to run
security_audit on the authentication system and vulnerability_scan on the web application."""


def assert_semantic_success() -> None:
    """Require implementation, code review, handoff, and security tool outputs."""
    messages = agency.thread_manager.get_all_messages()
    function_calls = {
        str(message.get("name"))
        for message in messages
        if isinstance(message, dict) and message.get("type") == "function_call"
    }
    tool_outputs = "\n".join(
        str(message.get("output", ""))
        for message in messages
        if isinstance(message, dict) and message.get("type") == "function_call_output"
    )

    required_calls = {
        "implement_feature",
        "review_code_quality",
        "security_audit",
        "send_message_with_context",
        "vulnerability_scan",
        "transfer_to_SecurityExpert",
    }
    missing_calls = sorted(required_calls - function_calls)
    if missing_calls:
        raise RuntimeError(f"Missing expected hybrid workflow calls: {missing_calls}")

    required_outputs = [
        "implemented with authentication middleware",
        "Code quality review complete",
        "Security audit complete",
        "Vulnerability scan",
    ]
    missing_outputs = [expected for expected in required_outputs if expected not in tool_outputs]
    if missing_outputs:
        raise RuntimeError(f"Missing expected hybrid workflow outputs: {missing_outputs}")

    print("\nSemantic check passed: implementation, code review, and security tools completed.")


async def run_non_interactive_demo(input_message: str = DEMO_PROMPT) -> None:
    """Run the README-style prompt without opening the TUI."""
    async for _ in agency.get_response_stream(input_message):
        pass
    assert_semantic_success()


if __name__ == "__main__":
    if "--non-interactive" in sys.argv:
        asyncio.run(run_non_interactive_demo())
    else:
        agency.tui()

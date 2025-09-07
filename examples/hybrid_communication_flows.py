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

It will open a terminal demo of the agency, where you can interact with the agency.
Ask ProjectManager to implement a new feature with code quality review and security audit.
For example, you can use the following input query:
'''
We need to implement a user authentication system for our web application.
This is a high priority item for our security review phase.
Please implement the feature and ensure it meets security standards.
'''
"""

import logging
import os
import sys

# Path setup so the example can be run standalone
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from pydantic import BaseModel, Field

from agency_swarm import Agency, Agent, ModelSettings, function_tool
from agency_swarm.tools.send_message import SendMessage, SendMessageHandoff

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

    class ExtraParams(BaseModel):
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

    def __init__(self, sender_agent: Agent, recipients: dict[str, Agent] | None = None) -> None:
        super().__init__(sender_agent, recipients)
        self.name = "send_message_with_context"


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
    send_message_tool_class=SendMessageWithProjectContext,
    model_settings=ModelSettings(temperature=0),
)

developer = Agent(
    name="Developer",
    description="Software developer who implements features and coordinates with security experts",
    instructions=(
        "You are a Senior Developer responsible for implementing software features. "
        "You have access to code quality review and feature implementation tools. "
        "When working on security-sensitive features, you must consult the SecurityExpert using handoff (transfer) tool. "
        "Always provide detailed technical responses including any tool outputs. "
        "When performing handoffs, transfer complete context including all technical details."
    ),
    tools=[review_code_quality, implement_feature],
    send_message_tool_class=SendMessageHandoff,
    model_settings=ModelSettings(temperature=0),
)

security_expert = Agent(
    name="SecurityExpert",
    description="Security specialist who performs audits and vulnerability assessments",
    instructions=(
        "You are a Security Expert specializing in application security audits. "
        "You have access to security audit and vulnerability scanning tools. "
        "Provide comprehensive security assessments with specific recommendations. "
        "Always run appropriate security tools and include complete findings in your response. "
        "Focus on practical, actionable security improvements."
    ),
    tools=[security_audit, vulnerability_scan],
    model_settings=ModelSettings(temperature=0),
)

agency = Agency(
    project_manager,
    communication_flows=[
        (project_manager > developer > security_expert),
    ],
    shared_instructions="Focus on delivering secure, high-quality software. Use project context to prioritize work.",
)


if __name__ == "__main__":
    agency.terminal_demo()

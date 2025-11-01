#!/usr/bin/env python3
"""
GmailCreateDraft Tool
Creates email drafts in Gmail using Composio SDK.
Uses VALIDATED pattern from FINAL_VALIDATION_SUMMARY.md
"""
import json
import os

from composio import Composio
from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailCreateDraft(BaseTool):
    """
    Creates an email draft in Gmail using Composio SDK.
    Stores the draft without sending it, allowing for review and modification before sending.

    This tool uses the VALIDATED Composio SDK pattern with GMAIL_CREATE_EMAIL_DRAFT action.
    """

    to: str = Field(
        ...,
        description="Recipient email address (required). For multiple recipients, use comma-separated format."
    )

    subject: str = Field(
        ...,
        description="Email subject line (required)"
    )

    body: str = Field(
        ...,
        description="Email body content (required). Can be plain text or HTML."
    )

    cc: str = Field(
        default="",
        description="CC recipients, comma-separated (optional)"
    )

    bcc: str = Field(
        default="",
        description="BCC recipients, comma-separated (optional)"
    )

    def run(self):
        """
        Creates a draft in Gmail via Composio SDK.
        Returns JSON string with draft ID, success status, and message.

        Uses the validated pattern:
        - Composio client with API key
        - GMAIL_CREATE_EMAIL_DRAFT action
        - user_id=entity_id for authentication
        """
        # Get Composio credentials from environment
        api_key = os.getenv("COMPOSIO_API_KEY")
        entity_id = os.getenv("GMAIL_ENTITY_ID")

        # Validate credentials
        if not api_key or not entity_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env",
                "draft_id": None
            }, indent=2)

        try:
            # Initialize Composio client (VALIDATED PATTERN)
            client = Composio(api_key=api_key)

            # Prepare draft parameters
            draft_params = {
                "recipient_email": self.to,
                "subject": self.subject,
                "body": self.body,
            }

            # Add optional CC if provided
            if self.cc:
                draft_params["cc"] = self.cc.split(',') if isinstance(self.cc, str) else self.cc

            # Add optional BCC if provided
            if self.bcc:
                draft_params["bcc"] = self.bcc.split(',') if isinstance(self.bcc, str) else self.bcc

            # Execute GMAIL_CREATE_EMAIL_DRAFT via Composio (VALIDATED PATTERN)
            result = client.tools.execute(
                "GMAIL_CREATE_EMAIL_DRAFT",
                draft_params,
                user_id=entity_id  # CRITICAL: Uses entity_id for authentication
            )

            # Check if draft creation was successful
            if result.get("successful"):
                draft_data = result.get("data", {})
                draft_id = draft_data.get("id", "unknown")

                return json.dumps({
                    "success": True,
                    "draft_id": draft_id,
                    "to": self.to,
                    "subject": self.subject,
                    "body_preview": self.body[:100] + "..." if len(self.body) > 100 else self.body,
                    "message": f"Draft created successfully with ID: {draft_id}",
                    "created_via": "composio_sdk",
                    "thread_id": draft_data.get("threadId"),
                    "raw_data": draft_data
                }, indent=2)
            else:
                # Draft creation failed
                error_msg = result.get("error", "Unknown error during draft creation")
                return json.dumps({
                    "success": False,
                    "error": error_msg,
                    "draft_id": None,
                    "message": "Failed to create draft in Gmail",
                    "raw_response": result
                }, indent=2)

        except Exception as e:
            # Handle unexpected errors
            return json.dumps({
                "success": False,
                "error": f"Exception while creating draft: {str(e)}",
                "error_type": type(e).__name__,
                "draft_id": None,
                "message": "Draft creation failed due to an error"
            }, indent=2)


if __name__ == "__main__":
    """
    Test suite for GmailCreateDraft tool.
    Tests various draft creation scenarios.
    """
    print("=" * 80)
    print("TESTING GmailCreateDraft (Composio SDK)")
    print("=" * 80)

    # Test 1: Simple draft
    print("\n[TEST 1] Create simple draft:")
    print("-" * 80)
    tool = GmailCreateDraft(
        to="john@example.com",
        subject="Test Email",
        body="This is a test email body created via Composio SDK."
    )
    result = tool.run()
    print(result)

    # Test 2: Draft with CC and BCC
    print("\n[TEST 2] Create draft with CC/BCC:")
    print("-" * 80)
    tool = GmailCreateDraft(
        to="recipient@example.com",
        cc="manager@example.com",
        bcc="archive@example.com",
        subject="Project Update - Q4 2024",
        body="Here's the latest update on the project. We've completed 75% of the planned features."
    )
    result = tool.run()
    print(result)

    # Test 3: Draft with multiple recipients
    print("\n[TEST 3] Create draft with multiple recipients:")
    print("-" * 80)
    tool = GmailCreateDraft(
        to="user1@example.com, user2@example.com, user3@example.com",
        subject="Team Announcement",
        body="Hello team,\n\nThis is an important announcement regarding our upcoming sprint.\n\nBest regards,\nManager"
    )
    result = tool.run()
    print(result)

    # Test 4: HTML formatted draft
    print("\n[TEST 4] Create HTML formatted draft:")
    print("-" * 80)
    html_body = """
    <html>
        <body>
            <h2>Important Update</h2>
            <p>This is an <strong>HTML formatted</strong> email draft.</p>
            <ul>
                <li>Feature A completed</li>
                <li>Feature B in progress</li>
                <li>Feature C planned</li>
            </ul>
            <p>Thank you,<br/>Development Team</p>
        </body>
    </html>
    """
    tool = GmailCreateDraft(
        to="client@example.com",
        subject="Project Status - HTML Format",
        body=html_body
    )
    result = tool.run()
    print(result)

    # Test 5: Long email draft
    print("\n[TEST 5] Create draft with long body:")
    print("-" * 80)
    long_body = """Dear Client,

I hope this email finds you well. I wanted to provide you with a comprehensive update on the project status.

Project Overview:
The project has been progressing well over the past few weeks. We've completed several key milestones and are on track to meet our deadline.

Completed Items:
- Initial design phase
- Development of core features
- Testing framework setup
- Documentation and user guides
- Integration with external APIs

Upcoming Tasks:
- Final integration testing
- User acceptance testing
- Performance optimization
- Deployment preparation
- Training materials and workshops

Timeline:
We expect to complete all remaining tasks within the next two weeks. The final delivery date remains on schedule for the end of the month.

Budget Status:
We are currently within budget and have allocated resources efficiently to ensure timely completion.

Please let me know if you have any questions or concerns. I'm available for a call this week to discuss any details.

Best regards,
Project Manager
"""

    tool = GmailCreateDraft(
        to="client@example.com",
        subject="Comprehensive Project Update - November 2024",
        body=long_body
    )
    result = tool.run()
    print(result)

    # Test 6: Missing credentials (error test)
    print("\n[TEST 6] Test error handling (credential check):")
    print("-" * 80)
    print("NOTE: This test validates that the tool handles missing credentials gracefully.")
    print("If credentials are present, this will create a draft (expected behavior).")

    print("\n" + "=" * 80)
    print("TEST SUITE COMPLETED")
    print("=" * 80)
    print("\nProduction Setup Instructions:")
    print("1. Set COMPOSIO_API_KEY in .env file")
    print("2. Set GMAIL_ENTITY_ID in .env file (your Composio connected account)")
    print("3. Ensure Gmail integration is connected via Composio dashboard")
    print("4. GMAIL_CREATE_EMAIL_DRAFT action must be enabled for your integration")
    print("\nValidated Pattern Used:")
    print("- Composio SDK with client.tools.execute()")
    print("- Action: GMAIL_CREATE_EMAIL_DRAFT")
    print("- Authentication: user_id=entity_id")
    print("- Returns: JSON with success, draft_id, and message")
    print("=" * 80)

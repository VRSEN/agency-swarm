import json
import os

from composio import Composio
from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailSendEmail(BaseTool):
    """
    Sends an email through Gmail API.
    Can send a saved draft by draft_id or compose and send a new email directly.
    """

    draft_id: str = Field(default="", description="Gmail draft ID to send (if sending an existing draft)")

    to: str = Field(default="", description="Recipient email address (required if not using draft_id)")

    subject: str = Field(default="", description="Email subject (required if not using draft_id)")

    body: str = Field(default="", description="Email body (required if not using draft_id)")

    cc: str = Field(default="", description="CC recipients, comma-separated")

    bcc: str = Field(default="", description="BCC recipients, comma-separated")

    def run(self):
        """
        Sends an email via Gmail API using Composio.
        Returns JSON string with message ID and send confirmation.
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        entity_id = os.getenv("GMAIL_ENTITY_ID")

        if not api_key or not entity_id:
            return json.dumps({
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env"
            })

        try:
            # Validate inputs
            if self.draft_id:
                return json.dumps({
                    "error": "Draft sending not yet implemented. Please compose and send directly.",
                    "note": "Use to, subject, and body parameters instead of draft_id"
                })

            # Composing and sending new email
            if not self.to or not self.subject or not self.body:
                return json.dumps({
                    "error": "Missing required fields: to, subject, and body are required"
                })

            # Initialize Composio client
            client = Composio(api_key=api_key)

            # Prepare email parameters
            email_params = {
                "recipient_email": self.to,
                "subject": self.subject,
                "body": self.body,
                "is_html": False
            }

            # Add CC if provided
            if self.cc:
                email_params["cc"] = self.cc.split(',') if isinstance(self.cc, str) else self.cc

            # Add BCC if provided
            if self.bcc:
                email_params["bcc"] = self.bcc.split(',') if isinstance(self.bcc, str) else self.bcc

            # Execute Gmail send via Composio
            result = client.tools.execute(
                "GMAIL_SEND_EMAIL",
                email_params,
                user_id=entity_id
            )

            # Format response
            if result.get("successful"):
                return json.dumps({
                    "success": True,
                    "message_id": result.get("data", {}).get("id"),
                    "thread_id": result.get("data", {}).get("threadId"),
                    "to": self.to,
                    "subject": self.subject,
                    "sent_via": "composio",
                    "message": "Email sent successfully via Composio Gmail integration"
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "message": "Failed to send email"
                }, indent=2)

        except Exception as e:
            return json.dumps({
                "error": f"Error sending email: {str(e)}",
                "type": type(e).__name__
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailSendEmail...")

    # Test 1: Send existing draft
    print("\n1. Send existing draft:")
    tool = GmailSendEmail(draft_id="draft_abc123")
    result = tool.run()
    print(result)

    # Test 2: Compose and send new email
    print("\n2. Compose and send new email:")
    tool = GmailSendEmail(
        to="john@example.com",
        subject="Meeting Confirmation",
        body="Hi John,\n\nConfirming our meeting tomorrow at 2 PM.\n\nBest regards,\nSarah",
    )
    result = tool.run()
    print(result)

    # Test 3: Send with CC and BCC
    print("\n3. Send with CC and BCC:")
    tool = GmailSendEmail(
        to="team@example.com",
        cc="manager@example.com",
        bcc="archive@example.com",
        subject="Team Update",
        body="Hello team,\n\nHere's this week's update...\n\nBest,\nLead",
    )
    result = tool.run()
    print(result)

    # Test 4: Missing required fields
    print("\n4. Test with missing fields (should error):")
    tool = GmailSendEmail(
        to="test@example.com",
        subject="Test",
        # Missing body
    )
    result = tool.run()
    print(result)

    # Test 5: Send urgent email
    print("\n5. Send urgent email:")
    tool = GmailSendEmail(
        to="support@hosting.com",
        subject="URGENT: Server Down",
        body="Our production server is currently down and affecting all users. "
        "Please investigate immediately.\n\nSeverity: Critical\nTime: Now\n\nThank you.",
    )
    result = tool.run()
    print(result)

    print("\nTest completed!")
    print("\nProduction setup:")
    print("- Requires Gmail API OAuth2 authentication")
    print("- Install google-api-python-client")
    print("- Use service.users().messages().send() for actual sending")
    print("- Use service.users().drafts().send() for draft sending")

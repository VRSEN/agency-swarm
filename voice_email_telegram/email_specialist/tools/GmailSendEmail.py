import base64
import json
import os
from email.mime.text import MIMEText

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
        Sends an email via Gmail API.
        Returns JSON string with message ID and send confirmation.
        """
        gmail_token = os.getenv("GMAIL_ACCESS_TOKEN")
        if not gmail_token:
            return json.dumps({"error": "GMAIL_ACCESS_TOKEN not found. Please authenticate with Gmail API."})

        try:
            # Validate inputs
            if self.draft_id:
                # Sending an existing draft
                message_id = f"msg_{hash(self.draft_id)}"
                result = {
                    "success": True,
                    "message_id": message_id,
                    "draft_id": self.draft_id,
                    "sent_via": "draft",
                    "message": "Email sent successfully (mock). In production, this would send the Gmail draft.",
                }
            else:
                # Composing and sending new email
                if not self.to or not self.subject or not self.body:
                    return json.dumps(
                        {"error": "Missing required fields: to, subject, and body are required when not using draft_id"}
                    )

                # Create MIME message
                message = MIMEText(self.body, "plain")
                message["To"] = self.to
                message["Subject"] = self.subject

                if self.cc:
                    message["Cc"] = self.cc
                if self.bcc:
                    message["Bcc"] = self.bcc

                # Encode message
                base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

                # Mock send
                message_id = f"msg_{hash(self.subject + self.to)}"
                result = {
                    "success": True,
                    "message_id": message_id,
                    "to": self.to,
                    "subject": self.subject,
                    "sent_via": "direct",
                    "message": "Email sent successfully (mock). In production, this would send via Gmail API.",
                }

            # Add note about production setup
            result["note"] = "This is a mock implementation. Set up Gmail API OAuth2 for production use."

            return json.dumps(result, indent=2)

        except Exception as e:
            return json.dumps({"error": f"Error sending email: {str(e)}"})


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

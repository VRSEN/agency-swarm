import json
import os
import requests

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailSendEmail(BaseTool):
    """
    Sends an email through Gmail API.
    Can send a saved draft by draft_id or compose and send a new email directly.
    Automatically appends "Cheers, Ashley" signature to all outgoing emails.
    """

    draft_id: str = Field(default="", description="Gmail draft ID to send (if sending an existing draft)")

    to: str = Field(default="", description="Recipient email address (required if not using draft_id)")

    subject: str = Field(default="", description="Email subject (required if not using draft_id)")

    body: str = Field(default="", description="Email body (required if not using draft_id)")

    cc: str = Field(default="", description="CC recipients, comma-separated")

    bcc: str = Field(default="", description="BCC recipients, comma-separated")

    skip_signature: bool = Field(
        default=False,
        description="Skip automatic signature append (use for replies or when signature already present)"
    )

    def _append_signature(self, body: str) -> str:
        """
        Appends signature to email body if not already present.

        Args:
            body: Email body text

        Returns:
            Body with signature appended
        """
        if not body:
            return "\n\nCheers, Ashley"

        # Check if signature already present
        signature = "Cheers, Ashley"
        if signature in body:
            return body

        # Clean trailing whitespace and append signature
        cleaned_body = body.rstrip()
        return f"{cleaned_body}\n\n{signature}"

    def run(self):
        """
        Sends an email via Gmail API using Composio REST API.
        Returns JSON string with message ID and send confirmation.
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        entity_id = os.getenv("GMAIL_CONNECTION_ID")

        if not api_key or not entity_id:
            return json.dumps({
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env"
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

            # Append signature to body (unless skipped)
            email_body = self.body
            if not self.skip_signature:
                email_body = self._append_signature(self.body)

            # Prepare email parameters
            email_params = {
                "recipient_email": self.to,
                "subject": self.subject,
                "body": email_body,
                "is_html": False
            }

            # Add CC if provided
            if self.cc:
                email_params["cc"] = self.cc.split(',') if isinstance(self.cc, str) else self.cc

            # Add BCC if provided
            if self.bcc:
                email_params["bcc"] = self.bcc.split(',') if isinstance(self.bcc, str) else self.bcc

            # Prepare API request
            url = "https://backend.composio.dev/api/v2/actions/GMAIL_SEND_EMAIL/execute"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "connectedAccountId": entity_id,
                "input": email_params
            }

            # Execute via Composio REST API
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()

            # Format response
            if result.get("successfull") or result.get("data"):
                data = result.get("data", {})
                return json.dumps({
                    "success": True,
                    "message_id": data.get("id"),
                    "thread_id": data.get("threadId"),
                    "to": self.to,
                    "subject": self.subject,
                    "signature_added": not self.skip_signature,
                    "sent_via": "composio",
                    "message": "Email sent successfully via Composio Gmail integration"
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "message": "Failed to send email"
                }, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "error": f"API request failed: {str(e)}",
                "type": "RequestException"
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "error": f"Error sending email: {str(e)}",
                "type": type(e).__name__
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailSendEmail with Signature...")

    # Test 1: Send with automatic signature
    print("\n1. Send with automatic signature:")
    tool = GmailSendEmail(
        to="john@example.com",
        subject="Meeting Confirmation",
        body="Hi John,\n\nConfirming our meeting tomorrow at 2 PM.\n\nBest regards",
    )
    result = tool.run()
    print(result)

    # Test 2: Send with signature already present
    print("\n2. Send with signature already in body (should not duplicate):")
    tool = GmailSendEmail(
        to="sarah@example.com",
        subject="Quick Update",
        body="Hi Sarah,\n\nJust a quick update.\n\nCheers, Ashley",
    )
    result = tool.run()
    print(result)

    # Test 3: Skip signature
    print("\n3. Send with skip_signature=True:")
    tool = GmailSendEmail(
        to="team@example.com",
        subject="Automated Report",
        body="This is an automated report. No signature needed.",
        skip_signature=True
    )
    result = tool.run()
    print(result)

    # Test 4: Send with CC and BCC
    print("\n4. Send with CC and BCC:")
    tool = GmailSendEmail(
        to="team@example.com",
        cc="manager@example.com",
        bcc="archive@example.com",
        subject="Team Update",
        body="Hello team,\n\nHere's this week's update...",
    )
    result = tool.run()
    print(result)

    # Test 5: Empty body (should add signature only)
    print("\n5. Empty body (signature only):")
    tool = GmailSendEmail(
        to="test@example.com",
        subject="Test",
        body="",
    )
    result = tool.run()
    print(result)

    # Test 6: Missing required fields
    print("\n6. Test with missing fields (should error):")
    tool = GmailSendEmail(
        to="test@example.com",
        subject="Test",
        # Missing body
    )
    result = tool.run()
    print(result)

    print("\nTest completed!")
    print("\nProduction setup:")
    print("- Requires COMPOSIO_API_KEY in .env")
    print("- Requires GMAIL_CONNECTION_ID in .env")
    print("- Gmail connected via Composio dashboard")
    print("- Signature 'Cheers, Ashley' automatically added to all emails")
    print("- Use skip_signature=True to disable signature for specific emails")

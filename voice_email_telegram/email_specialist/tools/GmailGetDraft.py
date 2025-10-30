from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import json
from dotenv import load_dotenv

load_dotenv()

class GmailGetDraft(BaseTool):
    """
    Retrieves a specific email draft from Gmail by draft ID.
    Used to fetch draft content for revision or review.
    """

    draft_id: str = Field(
        ...,
        description="Gmail draft ID to retrieve"
    )

    def run(self):
        """
        Fetches the draft from Gmail API.
        Returns JSON string with draft content (to, subject, body).
        """
        gmail_token = os.getenv("GMAIL_ACCESS_TOKEN")
        if not gmail_token:
            return json.dumps({
                "error": "GMAIL_ACCESS_TOKEN not found. Please authenticate with Gmail API."
            })

        try:
            # In production, this would make an API call to Gmail
            # For now, return mock data based on draft_id

            # Mock draft data
            mock_drafts = {
                "draft_abc123": {
                    "to": "john@acmecorp.com",
                    "subject": "Shipment Delay Update",
                    "body": "Hi John,\n\nI wanted to reach out regarding your recent order. Unfortunately, we've experienced a slight delay in shipping. The order will now arrive on Tuesday instead of Monday as originally scheduled.\n\nWe apologize for any inconvenience this may cause and appreciate your understanding.\n\nBest regards,\nSarah Johnson"
                },
                "draft_xyz789": {
                    "to": "sarah@supplier.com",
                    "subject": "Reorder Blue Widgets",
                    "body": "Hey Sarah,\n\nHope you're doing well! We'd like to reorder the blue widgets - we'll need 500 units this time.\n\nLet me know when you can get those shipped out.\n\nThanks!\nUser"
                }
            }

            if self.draft_id in mock_drafts:
                draft_data = mock_drafts[self.draft_id]
                result = {
                    "success": True,
                    "draft_id": self.draft_id,
                    "to": draft_data["to"],
                    "subject": draft_data["subject"],
                    "body": draft_data["body"],
                    "message": "Draft retrieved (mock data). In production, this would fetch from Gmail API."
                }
            else:
                # Generate generic mock data for unknown draft IDs
                result = {
                    "success": True,
                    "draft_id": self.draft_id,
                    "to": "recipient@example.com",
                    "subject": "Email Draft",
                    "body": "This is a mock draft body for testing purposes.",
                    "message": "Draft retrieved (mock). In production, this would fetch actual draft from Gmail."
                }

            result["note"] = "This is a mock implementation. Set up Gmail API OAuth2 for production use."

            return json.dumps(result, indent=2)

        except Exception as e:
            return json.dumps({
                "error": f"Error retrieving draft: {str(e)}"
            })


if __name__ == "__main__":
    print("Testing GmailGetDraft...")

    # Test 1: Get known draft
    print("\n1. Get known mock draft:")
    tool = GmailGetDraft(draft_id="draft_abc123")
    result = tool.run()
    print(result)

    # Test 2: Get another known draft
    print("\n2. Get another mock draft:")
    tool = GmailGetDraft(draft_id="draft_xyz789")
    result = tool.run()
    print(result)

    # Test 3: Get unknown draft
    print("\n3. Get unknown draft (generates generic mock):")
    tool = GmailGetDraft(draft_id="draft_unknown_123")
    result = tool.run()
    print(result)

    print("\nTest completed!")
    print("\nProduction implementation:")
    print("- Use service.users().drafts().get(userId='me', id=draft_id)")
    print("- Decode base64 message content")
    print("- Parse MIME message to extract to, subject, body")
    print("- Handle multipart messages (plain text + HTML)")

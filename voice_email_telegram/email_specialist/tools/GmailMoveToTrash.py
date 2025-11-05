#!/usr/bin/env python3
"""
GmailMoveToTrash Tool - Move Gmail messages to trash (soft delete, recoverable).

UPDATED: Uses Composio REST API directly instead of SDK (SDK has compatibility issues).
This approach matches the working GmailFetchEmails.py implementation.

Note: Trash != Permanent delete. Trashed messages can be recovered within 30 days.
After 30 days, Gmail automatically deletes trashed messages permanently.
"""
import json
import os
import requests

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailMoveToTrash(BaseTool):
    """
    Move Gmail message to trash (soft delete, recoverable).

    This action moves a message to trash rather than permanently deleting it.
    Trashed messages can be recovered from the Trash folder within 30 days.
    Gmail automatically permanently deletes trashed messages after 30 days.

    Use cases:
    - "Delete this email" (soft delete)
    - "Move to trash"
    - "Get rid of this message"

    For permanent deletion, use GmailDeleteMessage (cannot be undone).
    """

    message_id: str = Field(
        ...,
        description="Gmail message ID to move to trash (required). Example: '18c1f2a3b4d5e6f7'"
    )

    def run(self):
        """
        Executes GMAIL_MOVE_TO_TRASH via Composio REST API.

        Returns:
            JSON string with:
            - success: bool - Whether the operation was successful
            - message_id: str - The message ID that was trashed
            - status: str - Status message
            - error: str - Error message if failed
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        connection_id = os.getenv("GMAIL_CONNECTION_ID")

        if not api_key or not connection_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env",
                "message_id": self.message_id
            }, indent=2)

        try:
            # Validate message_id
            if not self.message_id or not self.message_id.strip():
                return json.dumps({
                    "success": False,
                    "error": "message_id is required and cannot be empty",
                    "message_id": self.message_id
                }, indent=2)

            # Prepare API request
            url = "https://backend.composio.dev/api/v2/actions/GMAIL_MOVE_TO_TRASH/execute"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "connectedAccountId": connection_id,
                "input": {
                    "message_id": self.message_id,
                    "user_id": "me"
                }
            }

            # Execute via Composio REST API
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()

            # Check if successful
            if result.get("successfull") or result.get("data", {}).get("id"):
                return json.dumps({
                    "success": True,
                    "message_id": self.message_id,
                    "status": "Message moved to trash",
                    "recoverable": True,
                    "recovery_period": "30 days",
                    "note": "Trashed messages are automatically deleted after 30 days"
                }, indent=2)
            else:
                error_msg = result.get("error", "Unknown error")
                return json.dumps({
                    "success": False,
                    "error": error_msg,
                    "message_id": self.message_id,
                    "status": "Failed to move message to trash"
                }, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "success": False,
                "error": f"API request failed: {str(e)}",
                "type": "RequestException",
                "message_id": self.message_id
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error moving message to trash: {str(e)}",
                "type": type(e).__name__,
                "message_id": self.message_id
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailMoveToTrash...")
    print("=" * 60)
    print("\nNOTE: This test requires:")
    print("- COMPOSIO_API_KEY set in .env")
    print("- GMAIL_CONNECTION_ID set in .env")
    print("- Valid Gmail message IDs")
    print("\nTrash vs Permanent Delete:")
    print("- TRASH: Recoverable for 30 days, auto-deleted after")
    print("- DELETE: Permanent, cannot be undone")
    print("=" * 60)

    # Test 1: Move a single message to trash
    print("\n1. Move message to trash (basic usage):")
    tool = GmailMoveToTrash(message_id="18c1f2a3b4d5e6f7")
    result = tool.run()
    print(result)

    # Test 2: Missing message_id (should error)
    print("\n2. Test with empty message_id (should error):")
    tool = GmailMoveToTrash(message_id="")
    result = tool.run()
    print(result)

    # Test 3: Whitespace-only message_id (should error)
    print("\n3. Test with whitespace message_id (should error):")
    tool = GmailMoveToTrash(message_id="   ")
    result = tool.run()
    print(result)

    # Test 4: Real-world example with actual message ID
    print("\n4. Real-world example (requires actual message ID):")
    print("   Replace 'REPLACE_WITH_REAL_MESSAGE_ID' with an actual message ID")
    tool = GmailMoveToTrash(message_id="REPLACE_WITH_REAL_MESSAGE_ID")
    result = tool.run()
    print(result)

    # Test 5: Simulate trashing spam
    print("\n5. Trashing spam message:")
    tool = GmailMoveToTrash(message_id="spam_msg_12345")
    result = tool.run()
    print(result)

    # Test 6: Simulate trashing promotional email
    print("\n6. Trashing promotional email:")
    tool = GmailMoveToTrash(message_id="promo_msg_67890")
    result = tool.run()
    print(result)

    print("\n" + "=" * 60)
    print("Test completed!")
    print("\n" + "=" * 60)
    print("IMPORTANT NOTES:")
    print("=" * 60)
    print("\n1. TRASH vs DELETE:")
    print("   - Trash: Soft delete, recoverable for 30 days")
    print("   - Delete: Permanent, cannot be undone")
    print("\n2. RECOVERY:")
    print("   - Trashed messages appear in 'Trash' folder")
    print("   - User can restore from Trash within 30 days")
    print("   - Gmail auto-deletes after 30 days")
    print("\n3. USE CASES:")
    print("   - User says 'delete this email' → Use TRASH (safer)")
    print("   - User says 'permanently delete' → Use DELETE (permanent)")
    print("\n4. PRODUCTION WORKFLOW:")
    print("   a. Fetch emails with GmailFetchEmails")
    print("   b. Extract message_id from email object")
    print("   c. Call GmailMoveToTrash with message_id")
    print("   d. Confirm success to user")
    print("\n5. EXAMPLE WORKFLOW:")
    print("   User: 'Delete emails from spam@example.com'")
    print("   Step 1: GmailFetchEmails(query='from:spam@example.com')")
    print("   Step 2: Extract message IDs from results")
    print("   Step 3: GmailMoveToTrash(message_id=each_id)")
    print("   Step 4: Report count of trashed messages")
    print("\n6. ERROR HANDLING:")
    print("   - Invalid message_id → Returns error")
    print("   - Message already trashed → Returns success (idempotent)")
    print("   - Message doesn't exist → Returns error")
    print("\n" + "=" * 60)
    print("Ready for production use!")
    print("=" * 60)

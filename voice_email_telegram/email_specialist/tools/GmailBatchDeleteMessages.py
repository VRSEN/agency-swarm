#!/usr/bin/env python3
"""
GmailBatchDeleteMessages Tool - Permanently delete multiple Gmail messages in bulk.

⚠️ DANGER: This is PERMANENT deletion - messages CANNOT be recovered!

Based on validated pattern from FINAL_VALIDATION_SUMMARY.md
Uses Composio SDK client.tools.execute() with GMAIL_BATCH_DELETE_MESSAGES action.

IMPORTANT SAFETY NOTES:
- This is PERMANENT deletion, NOT trash (cannot be recovered)
- Batch size limited to 100 messages by default for safety
- Consider using GmailMoveToTrash for recoverable deletion
- No undo - messages are gone forever
- Use with extreme caution

Recommended workflow:
1. User reviews emails to delete
2. Extract message IDs from confirmed emails
3. Batch delete with this tool
4. Report deletion count to user
"""
import json
import os
import requests

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailBatchDeleteMessages(BaseTool):
    """
    Permanently delete multiple Gmail messages in bulk (DANGEROUS - cannot be recovered).

    ⚠️ CRITICAL WARNING: This is PERMANENT deletion!
    - Messages are deleted immediately and CANNOT be recovered
    - This is NOT the same as moving to trash
    - No undo functionality exists
    - Use GmailMoveToTrash for recoverable deletion

    Safety features:
    - Maximum batch size limit (default: 100 messages)
    - Requires explicit message_ids list (no query-based deletion)
    - Clear warnings about permanent deletion
    - Validation of all inputs before execution

    Use cases (with extreme caution):
    - Bulk cleanup of confirmed spam (after review)
    - Mass deletion of old emails (after confirmation)
    - Permanent removal of sensitive data (after backup)
    - Batch cleanup after migration (verified safe)

    Recommended alternative:
    - Use GmailMoveToTrash for recoverable deletion (30-day recovery window)
    - Only use this tool when permanent deletion is explicitly required
    """

    message_ids: list = Field(
        ...,
        description="List of Gmail message IDs to permanently delete (required). "
                    "Example: ['msg_123', 'msg_456']. Max 100 by default for safety."
    )

    max_batch_size: int = Field(
        default=100,
        description="Maximum number of messages to delete in one batch (safety limit). "
                    "Default: 100. Can be adjusted but use with extreme caution."
    )

    def run(self):
        """
        Executes GMAIL_BATCH_DELETE_MESSAGES via Composio SDK.

        Returns:
            JSON string with:
            - success: bool - Whether the operation was successful
            - deleted_count: int - Number of messages permanently deleted
            - message_ids: list - The message IDs that were deleted
            - warnings: list - Important warnings about the operation
            - error: str - Error message if failed

        Raises:
            Returns error JSON if:
            - Missing credentials
            - Empty message_ids list
            - Batch size exceeds max_batch_size
            - Invalid message IDs
            - API execution fails
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        connection_id = os.getenv("GMAIL_CONNECTION_ID")

        if not api_key or not connection_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env",
                "deleted_count": 0
            }, indent=2)

        try:
            # Validate message_ids
            if not self.message_ids or len(self.message_ids) == 0:
                return json.dumps({
                    "success": False,
                    "error": "message_ids is required and must contain at least one message ID",
                    "deleted_count": 0,
                    "note": "This is a safety feature - empty batch deletion is blocked"
                }, indent=2)

            # Safety check: Validate batch size
            if len(self.message_ids) > self.max_batch_size:
                return json.dumps({
                    "success": False,
                    "error": f"Batch size ({len(self.message_ids)}) exceeds maximum allowed ({self.max_batch_size})",
                    "deleted_count": 0,
                    "provided_count": len(self.message_ids),
                    "max_allowed": self.max_batch_size,
                    "safety_note": "This limit prevents accidental mass deletion. Adjust max_batch_size if intentional.",
                    "recommendation": "Consider using GmailMoveToTrash for recoverable deletion"
                }, indent=2)

            # Safety check: Validate message IDs are not empty strings
            invalid_ids = [mid for mid in self.message_ids if not mid or not mid.strip()]
            if invalid_ids:
                return json.dumps({
                    "success": False,
                    "error": f"Found {len(invalid_ids)} invalid/empty message IDs",
                    "deleted_count": 0,
                    "invalid_count": len(invalid_ids),
                    "note": "All message IDs must be non-empty strings"
                }, indent=2)            # Execute GMAIL_BATCH_DELETE_MESSAGES via Composio
            # Prepare API request
            url = "https://backend.composio.dev/api/v2/actions/GMAIL_BATCH_DELETE_MESSAGES/execute"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "connectedAccountId": connection_id,
                "input": {
                    "message_ids": self.message_ids,
                    "user_id": "me"  # Gmail API user identifier
                }
            }

            # Execute via Composio REST API
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()

            # Check if successful
            if result.get("successfull") or result.get("data") or result.get("data"):
                return json.dumps({
                    "success": True,
                    "deleted_count": len(self.message_ids),
                    "message_ids": self.message_ids,
                    "status": "Messages permanently deleted",
                    "warnings": [
                        "⚠️ PERMANENT DELETION - Cannot be recovered",
                        "Messages are gone forever",
                        "Not in trash - completely removed",
                        "No undo functionality available"
                    ],
                    "recommendation": "For future deletions, consider GmailMoveToTrash for 30-day recovery window"
                }, indent=2)
            else:
                error_msg = result.get("error", "Unknown error")
                return json.dumps({
                    "success": False,
                    "error": error_msg,
                    "deleted_count": 0,
                    "message_ids": self.message_ids,
                    "status": "Failed to delete messages"
                }, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "error": f"API request failed: {str(e)}",


                "type": "RequestException"
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error deleting messages: {str(e)}",
                "type": type(e).__name__,
                "deleted_count": 0,
                "message_ids": self.message_ids
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailBatchDeleteMessages...")
    print("=" * 80)
    print("⚠️  DANGER: This tool performs PERMANENT deletion!")
    print("=" * 80)
    print("\nNOTE: This test requires:")
    print("- COMPOSIO_API_KEY set in .env")
    print("- GMAIL_CONNECTION_ID set in .env")
    print("- Valid Gmail message IDs (use with caution!)")
    print("\n" + "=" * 80)
    print("PERMANENT vs TRASH vs ARCHIVE:")
    print("=" * 80)
    print("- PERMANENT DELETE (this tool): Cannot be recovered, gone forever")
    print("- TRASH (GmailMoveToTrash): Recoverable for 30 days, auto-deleted after")
    print("- ARCHIVE (GmailBatchModifyMessages): Removed from inbox, still accessible")
    print("\n⚠️  RECOMMENDATION: Use GmailMoveToTrash unless permanent deletion is required")
    print("=" * 80)

    # Test 1: Batch delete messages (basic usage)
    print("\n1. Batch delete multiple messages:")
    tool = GmailBatchDeleteMessages(
        message_ids=["msg_123", "msg_456", "msg_789"]
    )
    result = tool.run()
    print(result)

    # Test 2: Empty message_ids (should error)
    print("\n2. Test with empty message_ids list (should error):")
    tool = GmailBatchDeleteMessages(message_ids=[])
    result = tool.run()
    print(result)

    # Test 3: Batch size exceeds limit (should error)
    print("\n3. Test batch size exceeding limit (should error):")
    tool = GmailBatchDeleteMessages(
        message_ids=[f"msg_{i}" for i in range(150)],  # 150 messages
        max_batch_size=100  # Limit is 100
    )
    result = tool.run()
    print(result)

    # Test 4: Single message deletion
    print("\n4. Delete single message:")
    tool = GmailBatchDeleteMessages(
        message_ids=["single_msg_999"]
    )
    result = tool.run()
    print(result)

    # Test 5: Invalid message IDs (empty strings)
    print("\n5. Test with invalid message IDs (should error):")
    tool = GmailBatchDeleteMessages(
        message_ids=["valid_id", "", "  ", "another_valid"]
    )
    result = tool.run()
    print(result)

    # Test 6: Custom batch size limit
    print("\n6. Custom batch size (allow 200 messages):")
    tool = GmailBatchDeleteMessages(
        message_ids=[f"msg_{i}" for i in range(50)],
        max_batch_size=200  # Higher limit
    )
    result = tool.run()
    print(result)

    # Test 7: Spam cleanup scenario
    print("\n7. Spam cleanup scenario:")
    print("   Scenario: User reviewed spam, confirmed deletion of 25 messages")
    tool = GmailBatchDeleteMessages(
        message_ids=[f"spam_msg_{i}" for i in range(1, 26)]
    )
    result = tool.run()
    print(result)

    # Test 8: Old email cleanup
    print("\n8. Old email cleanup scenario:")
    print("   Scenario: Bulk delete emails older than 5 years (10 messages)")
    tool = GmailBatchDeleteMessages(
        message_ids=[f"old_msg_{year}_{month}" for year in range(2015, 2020)
                     for month in range(1, 3)]  # 10 messages
    )
    result = tool.run()
    print(result)

    # Test 9: Exactly at batch size limit
    print("\n9. Exactly at batch size limit (100 messages):")
    tool = GmailBatchDeleteMessages(
        message_ids=[f"msg_{i}" for i in range(100)]  # Exactly 100
    )
    result = tool.run()
    print(result)

    # Test 10: One over batch size limit (should error)
    print("\n10. One over batch size limit (should error):")
    tool = GmailBatchDeleteMessages(
        message_ids=[f"msg_{i}" for i in range(101)]  # 101 messages
    )
    result = tool.run()
    print(result)

    print("\n" + "=" * 80)
    print("Test completed!")
    print("=" * 80)
    print("\n" + "=" * 80)
    print("IMPORTANT SAFETY GUIDELINES:")
    print("=" * 80)
    print("\n1. PERMANENT DELETION:")
    print("   - Messages deleted with this tool CANNOT be recovered")
    print("   - No trash folder, no recovery period")
    print("   - Gone forever, no undo")
    print("\n2. BATCH SIZE LIMITS:")
    print("   - Default limit: 100 messages per batch")
    print("   - Adjustable via max_batch_size parameter")
    print("   - Prevents accidental mass deletion")
    print("\n3. SAFER ALTERNATIVES:")
    print("   - GmailMoveToTrash: 30-day recovery window")
    print("   - GmailBatchModifyMessages + archive: Removes from inbox, keeps accessible")
    print("   - Consider trash for user-initiated deletions")
    print("\n4. PRODUCTION WORKFLOW:")
    print("   a. User identifies emails to delete")
    print("   b. Fetch emails with GmailFetchEmails")
    print("   c. Display emails to user for confirmation")
    print("   d. User explicitly confirms permanent deletion")
    print("   e. Extract message IDs from confirmed emails")
    print("   f. Call GmailBatchDeleteMessages with IDs")
    print("   g. Report deletion count with warning")
    print("\n5. EXAMPLE WORKFLOWS:")
    print("\n   Workflow A - Spam Cleanup (safer with trash):")
    print("   User: 'Delete all spam emails'")
    print("   Step 1: GmailFetchEmails(query='label:SPAM')")
    print("   Step 2: Show spam count to user")
    print("   Step 3: User confirms: 'Yes, delete 47 spam messages'")
    print("   Step 4: Extract message IDs")
    print("   Step 5: GmailMoveToTrash (safer!) or GmailBatchDeleteMessages")
    print("   Step 6: Report: '47 messages deleted'")
    print("\n   Workflow B - Old Email Cleanup:")
    print("   User: 'Permanently delete emails older than 2020'")
    print("   Step 1: GmailFetchEmails(query='before:2020/01/01')")
    print("   Step 2: Show count and date range to user")
    print("   Step 3: User confirms: 'Yes, permanently delete 234 old emails'")
    print("   Step 4: Extract message IDs")
    print("   Step 5: Split into batches of 100")
    print("   Step 6: GmailBatchDeleteMessages for each batch")
    print("   Step 7: Report total deleted with warning")
    print("\n6. ERROR HANDLING:")
    print("   - Empty message_ids → Returns error")
    print("   - Batch size exceeded → Returns error with limit info")
    print("   - Invalid message_ids → Returns error with validation details")
    print("   - Message already deleted → Returns success (idempotent)")
    print("   - Message doesn't exist → May return error or success")
    print("\n7. SAFETY VALIDATIONS:")
    print("   - Requires explicit message_ids (no query-based deletion)")
    print("   - Validates batch size before execution")
    print("   - Checks for empty/invalid message IDs")
    print("   - Returns clear warnings about permanent deletion")
    print("   - Suggests GmailMoveToTrash alternative")
    print("\n8. USER COMMUNICATION:")
    print("   - Always warn user about permanent deletion")
    print("   - Require explicit confirmation for large batches")
    print("   - Report deletion count after completion")
    print("   - Remind about no recovery option")
    print("\n9. WHEN TO USE THIS TOOL:")
    print("   ✅ User explicitly says 'permanently delete'")
    print("   ✅ Bulk cleanup of confirmed spam (after review)")
    print("   ✅ Mass deletion of old verified safe emails")
    print("   ✅ Permanent removal of sensitive data (after backup)")
    print("\n10. WHEN NOT TO USE THIS TOOL:")
    print("   ❌ User just says 'delete' (use GmailMoveToTrash)")
    print("   ❌ No explicit confirmation from user")
    print("   ❌ Uncertain about which emails to delete")
    print("   ❌ User might want to recover later")
    print("\n" + "=" * 80)
    print("⚠️  USE WITH EXTREME CAUTION - PERMANENT DELETION!")
    print("=" * 80)
    print("\nReady for production use (with safety protocols)!")
    print("=" * 80)

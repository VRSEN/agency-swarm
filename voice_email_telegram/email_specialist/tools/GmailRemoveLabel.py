#!/usr/bin/env python3
"""
GmailRemoveLabel Tool - PERMANENTLY deletes a custom Gmail label using Composio SDK.

IMPORTANT: This deletes the LABEL itself, not emails
- Emails keep their messages
- Only the label tag is removed from all emails
- The label is permanently deleted

Based on validated pattern from FINAL_VALIDATION_SUMMARY.md
Uses Composio SDK client.tools.execute() with GMAIL_REMOVE_LABEL action.
"""
import json
import os

from composio import Composio
from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailRemoveLabel(BaseTool):
    """
    PERMANENTLY delete a custom Gmail label (and remove it from all emails).

    WARNING: This action is PERMANENT and CANNOT be undone!

    What happens:
    - The label is permanently deleted
    - The label is removed from ALL emails that have it
    - Emails themselves are NOT deleted (only the label tag is removed)
    - System labels CANNOT be deleted (INBOX, SENT, STARRED, etc.)

    Safety restrictions:
    - Only custom (user-created) labels can be deleted
    - System labels are protected and cannot be deleted
    - Label removed from ALL messages that have it
    - Action is PERMANENT (cannot undo)

    Use cases:
    - "Delete the 'Old Project' label"
    - Clean up unused custom labels
    - Remove deprecated label categories

    To get label IDs:
    - Use GmailListLabels tool to see all labels and their IDs
    - Only delete labels with type="user" (custom labels)

    Related tools:
    - GmailListLabels: List all labels to find the label_id
    - GmailCreateLabel: Create new custom labels
    - GmailAddLabel: Add labels to messages
    - GmailBatchModifyMessages: Remove label from specific messages (without deleting the label)
    """

    label_id: str = Field(
        ...,
        description="Label ID to permanently delete (required). Example: 'Label_123'. Get from GmailListLabels tool. CANNOT delete system labels like INBOX, SENT, etc."
    )

    def run(self):
        """
        Executes GMAIL_REMOVE_LABEL via Composio SDK.

        Returns:
            JSON string with:
            - success: bool - Whether deletion was successful
            - deleted_label_id: str - The label ID that was deleted
            - warning: str - Warning about permanent deletion
            - error: str - Error message if failed
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        entity_id = os.getenv("GMAIL_ENTITY_ID")

        if not api_key or not entity_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env",
                "deleted_label_id": None
            }, indent=2)

        try:
            # Validate inputs
            if not self.label_id:
                return json.dumps({
                    "success": False,
                    "error": "label_id is required",
                    "deleted_label_id": None
                }, indent=2)

            # Safety check: Prevent deletion of system labels
            SYSTEM_LABELS = [
                "INBOX", "SENT", "DRAFT", "TRASH", "SPAM", "IMPORTANT",
                "STARRED", "UNREAD", "CHAT", "CATEGORY_PERSONAL",
                "CATEGORY_SOCIAL", "CATEGORY_PROMOTIONS", "CATEGORY_UPDATES",
                "CATEGORY_FORUMS"
            ]

            if self.label_id.upper() in SYSTEM_LABELS:
                return json.dumps({
                    "success": False,
                    "error": f"Cannot delete system label '{self.label_id}'. Only custom labels can be deleted.",
                    "deleted_label_id": None,
                    "safety_warning": "System labels (INBOX, SENT, STARRED, etc.) are protected"
                }, indent=2)

            # Initialize Composio client
            client = Composio(api_key=api_key)

            # Prepare parameters for removing label
            params = {
                "label_id": self.label_id,
                "user_id": "me"
            }

            # Execute Gmail remove label via Composio
            result = client.tools.execute(
                "GMAIL_REMOVE_LABEL",
                params,
                user_id=entity_id
            )

            # Check if successful
            if result.get("successful"):
                return json.dumps({
                    "success": True,
                    "deleted_label_id": self.label_id,
                    "message": f"Label '{self.label_id}' has been permanently deleted",
                    "warning": "This action is PERMANENT. The label has been removed from all emails.",
                    "note": "Emails that had this label still exist, only the label tag was removed"
                }, indent=2)
            else:
                error_msg = result.get("error", "Unknown error")
                return json.dumps({
                    "success": False,
                    "error": error_msg,
                    "deleted_label_id": None,
                    "message": "Failed to delete label"
                }, indent=2)

        except Exception as e:
            error_message = str(e)

            # Enhanced error handling for common issues
            if "not found" in error_message.lower():
                return json.dumps({
                    "success": False,
                    "error": f"Label '{self.label_id}' not found. Use GmailListLabels to see available labels.",
                    "deleted_label_id": None,
                    "type": type(e).__name__
                }, indent=2)
            elif "permission" in error_message.lower():
                return json.dumps({
                    "success": False,
                    "error": f"Permission denied. Cannot delete label '{self.label_id}'. It may be a system label.",
                    "deleted_label_id": None,
                    "type": type(e).__name__
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": f"Error deleting label: {error_message}",
                    "deleted_label_id": None,
                    "type": type(e).__name__
                }, indent=2)


if __name__ == "__main__":
    print("Testing GmailRemoveLabel...")
    print("=" * 80)
    print("WARNING: These tests will PERMANENTLY delete labels if run with real data!")
    print("=" * 80)

    # Test 1: Attempt to delete system label (should fail with safety warning)
    print("\n1. Attempt to delete INBOX (should fail - system label protected):")
    tool = GmailRemoveLabel(label_id="INBOX")
    result = tool.run()
    print(result)

    # Test 2: Attempt to delete STARRED (should fail)
    print("\n2. Attempt to delete STARRED (should fail - system label protected):")
    tool = GmailRemoveLabel(label_id="STARRED")
    result = tool.run()
    print(result)

    # Test 3: Attempt to delete IMPORTANT (should fail)
    print("\n3. Attempt to delete IMPORTANT (should fail - system label protected):")
    tool = GmailRemoveLabel(label_id="IMPORTANT")
    result = tool.run()
    print(result)

    # Test 4: Delete custom label (mock - would work with real label ID)
    print("\n4. Delete custom label (example with Label_123):")
    print("NOTE: This would permanently delete the label if it exists!")
    tool = GmailRemoveLabel(label_id="Label_123")
    result = tool.run()
    print(result)

    # Test 5: Missing label_id (should error)
    print("\n5. Test with missing label_id (should error):")
    tool = GmailRemoveLabel(label_id="")
    result = tool.run()
    print(result)

    # Test 6: Delete category label (should fail - system label)
    print("\n6. Attempt to delete CATEGORY_SOCIAL (should fail - system label):")
    tool = GmailRemoveLabel(label_id="CATEGORY_SOCIAL")
    result = tool.run()
    print(result)

    print("\n" + "=" * 80)
    print("Test completed!")
    print("\n" + "=" * 80)

    print("\nIMPORTANT SAFETY NOTES:")
    print("1. This tool PERMANENTLY deletes labels - cannot be undone!")
    print("2. System labels (INBOX, SENT, STARRED, etc.) CANNOT be deleted")
    print("3. Only custom (user-created) labels can be deleted")
    print("4. When a label is deleted, it's removed from ALL emails")
    print("5. Emails themselves are NOT deleted, only the label tag is removed")

    print("\nUSAGE WORKFLOW:")
    print("Step 1: Use GmailListLabels to see all labels and their IDs")
    print("Step 2: Identify the label_id you want to delete (e.g., 'Label_123')")
    print("Step 3: Verify it's a custom label (type='user')")
    print("Step 4: Use this tool to permanently delete it")

    print("\nEXAMPLES:")
    print("User: 'Delete the Old Project label'")
    print("  → First: GmailListLabels to find 'Label_OldProject' ID")
    print("  → Then: GmailRemoveLabel(label_id='Label_OldProject')")

    print("\nUser: 'Clean up my unused labels'")
    print("  → First: GmailListLabels to see all custom labels")
    print("  → Then: GmailRemoveLabel for each unused label")

    print("\nRELATED TOOLS:")
    print("- GmailListLabels: List all labels to find IDs")
    print("- GmailCreateLabel: Create new custom labels")
    print("- GmailAddLabel: Add labels to specific messages")
    print("- GmailBatchModifyMessages: Remove label from messages WITHOUT deleting it")

    print("\nPRODUCTION REQUIREMENTS:")
    print("- Set COMPOSIO_API_KEY in .env")
    print("- Set GMAIL_ENTITY_ID in .env")
    print("- Gmail account connected via Composio")
    print("- User confirmation recommended before deletion")

    print("\n" + "=" * 80)

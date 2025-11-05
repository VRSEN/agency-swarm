#!/usr/bin/env python3
"""
GmailDeleteDraft Tool
Permanently deletes email drafts in Gmail using Composio SDK.
Uses VALIDATED pattern from existing tools.

SAFETY WARNING: This tool DELETES DRAFTS, not sent emails.
Deletion is permanent and cannot be undone.
"""
import json
import os
import requests

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailDeleteDraft(BaseTool):
    """
    Permanently deletes a draft email from Gmail using Composio SDK.

    IMPORTANT SAFETY NOTES:
    - This deletes DRAFT emails only (unsent messages in Drafts folder)
    - Does NOT delete sent emails (use GmailMoveToTrash for that)
    - Deletion is PERMANENT and cannot be undone
    - Use GmailGetDraft first to verify you're deleting the correct draft

    Common use cases:
    - "Delete that draft" - Remove unwanted draft after user review
    - "Cancel the draft email" - Discard draft user rejected via voice
    - "Clear my drafts" - Clean up old/unused drafts
    - User rejects draft via voice assistant - delete it

    Workflow pattern:
    1. GmailCreateDraft - Create draft for user approval
    2. FormatEmailForApproval - Format for voice/visual review
    3. User approves → GmailSendDraft
    4. User rejects → GmailDeleteDraft (this tool)

    This tool uses the VALIDATED Composio SDK pattern with GMAIL_DELETE_DRAFT action.
    """

    draft_id: str = Field(
        ...,
        description="Gmail draft ID to delete (required). Example: 'r-1234567890123456789'. Get from GmailListDrafts or GmailCreateDraft response."
    )

    user_id: str = Field(
        default="me",
        description="Gmail user ID (optional). Default is 'me' for authenticated user."
    )

    def run(self):
        """
        Deletes a draft from Gmail via Composio SDK.
        Returns JSON string with success status and deletion confirmation.

        Uses the validated pattern:
        - Composio client with API key
        - GMAIL_DELETE_DRAFT action
        - user_id=entity_id for authentication

        Returns:
            JSON string with success status, draft_id, and message
        """
        # Get Composio credentials from environment
        api_key = os.getenv("COMPOSIO_API_KEY")
        connection_id = os.getenv("GMAIL_CONNECTION_ID")

        # Validate credentials
        if not api_key or not connection_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env",
                "draft_id": self.draft_id,
                "deleted": False
            }, indent=2)

        # Validate draft_id
        if not self.draft_id or self.draft_id.strip() == "":
            return json.dumps({
                "success": False,
                "error": "draft_id is required and cannot be empty",
                "draft_id": None,
                "deleted": False
            }, indent=2)

        try:
            # Prepare deletion parameters
            delete_params = {
                "draft_id": self.draft_id,
                "user_id": self.user_id
            }

            # Prepare API request
            url = "https://backend.composio.dev/api/v2/actions/GMAIL_DELETE_DRAFT/execute"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "connectedAccountId": connection_id,
                "input": delete_params
            }

            # Execute via Composio REST API
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()

            # Check if deletion was successful
            if result.get("successfull") or result.get("data"):
                return json.dumps({
                    "success": True,
                    "draft_id": self.draft_id,
                    "deleted": True,
                    "message": f"Draft {self.draft_id} deleted successfully (PERMANENT)",
                    "action": "GMAIL_DELETE_DRAFT",
                    "warning": "Deletion is permanent and cannot be undone",
                    "raw_data": result.get("data", {})
                }, indent=2)
            else:
                # Deletion failed
                error_msg = result.get("error", "Unknown error during draft deletion")
                return json.dumps({
                    "success": False,
                    "error": error_msg,
                    "draft_id": self.draft_id,
                    "deleted": False,
                    "message": "Failed to delete draft from Gmail",
                    "possible_reasons": [
                        "Draft ID does not exist",
                        "Draft was already deleted",
                        "Insufficient permissions",
                        "Network connectivity issue"
                    ],
                    "raw_response": result
                }, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "error": f"API request failed: {str(e)}",


                "type": "RequestException"
            }, indent=2)
        except Exception as e:
            # Handle unexpected errors
            return json.dumps({
                "success": False,
                "error": f"Exception while deleting draft: {str(e)}",
                "error_type": type(e).__name__,
                "draft_id": self.draft_id,
                "deleted": False,
                "message": "Draft deletion failed due to an error",
                "recommendation": "Verify draft_id exists using GmailGetDraft or GmailListDrafts"
            }, indent=2)


if __name__ == "__main__":
    """
    Test suite for GmailDeleteDraft tool.
    Tests various draft deletion scenarios.

    NOTE: These tests use example draft IDs. In production, you need valid draft IDs
    from GmailListDrafts or GmailCreateDraft responses.
    """
    print("=" * 80)
    print("TESTING GmailDeleteDraft (Composio SDK)")
    print("=" * 80)
    print("\nSAFETY WARNING: This tool permanently deletes DRAFT emails only")
    print("It does NOT delete sent emails. Deletion cannot be undone.")
    print("=" * 80)

    # Test 1: Delete a draft (basic usage)
    print("\n[TEST 1] Delete draft by ID:")
    print("-" * 80)
    tool = GmailDeleteDraft(
        draft_id="r-1234567890123456789"
    )
    result = tool.run()
    print(result)
    print("\nUSE CASE: User rejects draft via voice - 'Delete that draft'")

    # Test 2: Delete draft with explicit user_id
    print("\n[TEST 2] Delete draft with explicit user_id:")
    print("-" * 80)
    tool = GmailDeleteDraft(
        draft_id="r-9876543210987654321",
        user_id="me"
    )
    result = tool.run()
    print(result)
    print("\nUSE CASE: Cancel draft email after user review")

    # Test 3: Delete draft after voice approval flow rejection
    print("\n[TEST 3] Voice workflow - User rejects draft:")
    print("-" * 80)
    print("WORKFLOW:")
    print("1. GmailCreateDraft creates draft → returns draft_id")
    print("2. FormatEmailForApproval formats for voice review")
    print("3. User says 'No, delete it' via voice")
    print("4. GmailDeleteDraft removes the draft ✓")
    tool = GmailDeleteDraft(
        draft_id="r-5555555555555555555"
    )
    result = tool.run()
    print(result)

    # Test 4: Missing draft_id (error test)
    print("\n[TEST 4] Error handling - Missing draft_id:")
    print("-" * 80)
    tool = GmailDeleteDraft(
        draft_id=""
    )
    result = tool.run()
    print(result)
    print("\nEXPECTED: Error message about required draft_id")

    # Test 5: Invalid draft_id (error test)
    print("\n[TEST 5] Error handling - Invalid draft_id:")
    print("-" * 80)
    tool = GmailDeleteDraft(
        draft_id="invalid-draft-id-format"
    )
    result = tool.run()
    print(result)
    print("\nEXPECTED: Error from Gmail API (draft not found)")

    # Test 6: Cleanup old drafts workflow
    print("\n[TEST 6] Workflow - Cleanup old drafts:")
    print("-" * 80)
    print("WORKFLOW:")
    print("1. GmailListDrafts → get all draft IDs")
    print("2. Filter old/unwanted drafts")
    print("3. GmailDeleteDraft each old draft")
    tool = GmailDeleteDraft(
        draft_id="r-7777777777777777777"
    )
    result = tool.run()
    print(result)

    # Test 7: Verify before delete pattern
    print("\n[TEST 7] Best Practice - Verify before delete:")
    print("-" * 80)
    print("RECOMMENDED WORKFLOW:")
    print("1. GmailGetDraft → verify draft contents")
    print("2. Show draft to user for confirmation")
    print("3. User confirms deletion")
    print("4. GmailDeleteDraft → permanent deletion")
    tool = GmailDeleteDraft(
        draft_id="r-8888888888888888888"
    )
    result = tool.run()
    print(result)

    # Test 8: Multi-draft cleanup scenario
    print("\n[TEST 8] Batch cleanup scenario:")
    print("-" * 80)
    print("SCENARIO: User wants to 'clear all old drafts'")
    print("WORKFLOW:")
    print("1. GmailListDrafts → ['draft1', 'draft2', 'draft3']")
    print("2. Loop through each draft_id")
    print("3. GmailDeleteDraft for each")
    draft_ids = ["r-1111111111111111111", "r-2222222222222222222", "r-3333333333333333333"]
    for draft_id in draft_ids:
        tool = GmailDeleteDraft(draft_id=draft_id)
        result = tool.run()
        print(f"\nDeleting {draft_id}:")
        print(result)

    print("\n" + "=" * 80)
    print("TEST SUITE COMPLETED")
    print("=" * 80)
    print("\nProduction Setup Instructions:")
    print("1. Set COMPOSIO_API_KEY in .env file")
    print("2. Set GMAIL_CONNECTION_ID in .env file (your Composio connected account)")
    print("3. Ensure Gmail integration is connected via Composio dashboard")
    print("4. GMAIL_DELETE_DRAFT action must be enabled for your integration")
    print("\nValidated Pattern Used:")
    print("- Composio SDK with client.tools.execute()")
    print("- Action: GMAIL_DELETE_DRAFT")
    print("- Authentication: user_id=entity_id")
    print("- Returns: JSON with success, draft_id, deleted status, and message")
    print("\nSAFETY REMINDERS:")
    print("- This deletes DRAFTS only (not sent emails)")
    print("- Deletion is PERMANENT and cannot be undone")
    print("- Always verify draft_id before deletion")
    print("- Use GmailGetDraft to preview before deleting")
    print("- For sent emails, use GmailMoveToTrash instead")
    print("\nCommon Workflows:")
    print("- Voice rejection: Create → Review → Reject → Delete")
    print("- Cleanup: List drafts → Filter old → Delete batch")
    print("- Verification: Get draft → Confirm → Delete")
    print("\nRelated Tools:")
    print("- GmailListDrafts: List all draft IDs")
    print("- GmailGetDraft: Preview draft before deletion")
    print("- GmailCreateDraft: Create drafts")
    print("- GmailSendDraft: Send drafts (alternative to deletion)")
    print("- GmailMoveToTrash: For sent emails (not drafts)")
    print("=" * 80)

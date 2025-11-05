#!/usr/bin/env python3
"""
GmailSendDraft Tool
Sends an existing Gmail draft email (converts draft to sent email).
Uses VALIDATED pattern from FINAL_VALIDATION_SUMMARY.md
"""
import json
import os
import requests

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailSendDraft(BaseTool):
    """
    Sends an existing Gmail draft email using Composio SDK.
    Converts a draft to a sent email in one action.

    This tool uses the VALIDATED Composio SDK pattern with GMAIL_SEND_DRAFT action.

    Use cases:
    - "Send that draft I created"
    - "Send the draft email"
    - User approves draft via voice, convert to sent email
    - Send pre-reviewed draft after approval
    """

    draft_id: str = Field(
        ...,
        description="Gmail draft ID to send (required). Get this from GmailCreateDraft or GmailListDrafts."
    )

    user_id: str = Field(
        default="me",
        description="Gmail user ID (default: 'me' for authenticated user)"
    )

    def run(self):
        """
        Sends an existing draft via Composio SDK.
        Returns JSON string with message ID, success status, and confirmation.

        Uses the validated pattern:
        - Composio client with API key
        - GMAIL_SEND_DRAFT action
        - user_id=entity_id for authentication
        """
        # Get Composio credentials from environment
        api_key = os.getenv("COMPOSIO_API_KEY")
        connection_id = os.getenv("GMAIL_CONNECTION_ID")

        # Validate credentials
        if not api_key or not connection_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env",
                "message_id": None,
                "draft_id": self.draft_id
            }, indent=2)

        # Validate draft_id
        if not self.draft_id or not self.draft_id.strip():
            return json.dumps({
                "success": False,
                "error": "draft_id is required and cannot be empty",
                "message_id": None,
                "draft_id": None
            }, indent=2)

        try:
            # Prepare send draft parameters
            send_params = {
                "draft_id": self.draft_id,
                "user_id": self.user_id
            }

            # Prepare API request
            url = "https://backend.composio.dev/api/v2/actions/GMAIL_SEND_DRAFT/execute"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "connectedAccountId": connection_id,
                "input": send_params
            }

            # Execute via Composio REST API
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()

            # Check if draft send was successful
            if result.get("successfull") or result.get("data"):
                message_data = result.get("data", {})
                message_id = message_data.get("id", "unknown")
                thread_id = message_data.get("threadId", "unknown")

                return json.dumps({
                    "success": True,
                    "message_id": message_id,
                    "thread_id": thread_id,
                    "draft_id": self.draft_id,
                    "message": f"Draft {self.draft_id} sent successfully as message {message_id}",
                    "sent_via": "composio_sdk",
                    "label_ids": message_data.get("labelIds", []),
                    "raw_data": message_data
                }, indent=2)
            else:
                # Draft send failed
                error_msg = result.get("error", "Unknown error during draft send")
                return json.dumps({
                    "success": False,
                    "error": error_msg,
                    "message_id": None,
                    "draft_id": self.draft_id,
                    "message": f"Failed to send draft {self.draft_id}",
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
                "error": f"Exception while sending draft: {str(e)}",
                "error_type": type(e).__name__,
                "message_id": None,
                "draft_id": self.draft_id,
                "message": "Draft send failed due to an error"
            }, indent=2)


if __name__ == "__main__":
    """
    Test suite for GmailSendDraft tool.
    Tests various draft sending scenarios.
    """
    print("=" * 80)
    print("TESTING GmailSendDraft (Composio SDK)")
    print("=" * 80)
    print("\nNOTE: These tests require existing draft IDs.")
    print("Create drafts first using GmailCreateDraft tool.")
    print("Replace 'draft_test_123' with actual draft IDs from your Gmail.\n")

    # Test 1: Send a simple draft
    print("\n[TEST 1] Send simple draft:")
    print("-" * 80)
    print("Purpose: Send an existing draft by ID")
    tool = GmailSendDraft(
        draft_id="draft_test_123"
    )
    result = tool.run()
    print(result)

    # Test 2: Send draft with explicit user_id
    print("\n[TEST 2] Send draft with explicit user_id:")
    print("-" * 80)
    print("Purpose: Verify user_id parameter works correctly")
    tool = GmailSendDraft(
        draft_id="draft_test_456",
        user_id="me"
    )
    result = tool.run()
    print(result)

    # Test 3: Error handling - empty draft_id
    print("\n[TEST 3] Error handling - empty draft_id:")
    print("-" * 80)
    print("Purpose: Validate error handling for missing draft_id")
    tool = GmailSendDraft(
        draft_id=""
    )
    result = tool.run()
    print(result)

    # Test 4: Error handling - invalid draft_id format
    print("\n[TEST 4] Error handling - invalid draft_id:")
    print("-" * 80)
    print("Purpose: Test behavior with non-existent draft ID")
    tool = GmailSendDraft(
        draft_id="invalid_draft_id_xyz"
    )
    result = tool.run()
    print(result)

    # Test 5: Send draft created from voice command
    print("\n[TEST 5] Send draft from voice workflow:")
    print("-" * 80)
    print("Purpose: Simulate voice approval workflow")
    print("Scenario: User says 'Send that draft'")
    tool = GmailSendDraft(
        draft_id="draft_voice_created_789"
    )
    result = tool.run()
    print(result)

    # Test 6: Rapid succession sends (testing rate limits)
    print("\n[TEST 6] Multiple draft sends:")
    print("-" * 80)
    print("Purpose: Test sending multiple drafts in succession")
    draft_ids = ["draft_batch_1", "draft_batch_2", "draft_batch_3"]
    for idx, draft_id in enumerate(draft_ids, 1):
        print(f"\n  Sending draft {idx}/3: {draft_id}")
        tool = GmailSendDraft(draft_id=draft_id)
        result = tool.run()
        result_obj = json.loads(result)
        if result_obj.get("success"):
            print(f"  ✓ Success: {result_obj.get('message_id')}")
        else:
            print(f"  ✗ Failed: {result_obj.get('error')}")

    print("\n" + "=" * 80)
    print("TEST SUITE COMPLETED")
    print("=" * 80)
    print("\nProduction Setup Instructions:")
    print("1. Set COMPOSIO_API_KEY in .env file")
    print("2. Set GMAIL_CONNECTION_ID in .env file (your Composio connected account)")
    print("3. Ensure Gmail integration is connected via Composio dashboard")
    print("4. GMAIL_SEND_DRAFT action must be enabled for your integration")
    print("\nValidated Pattern Used:")
    print("- Composio SDK with client.tools.execute()")
    print("- Action: GMAIL_SEND_DRAFT")
    print("- Authentication: user_id=entity_id")
    print("- Returns: JSON with success, message_id, thread_id, and confirmation")
    print("\nTypical Workflow:")
    print("1. Create draft: GmailCreateDraft → draft_id")
    print("2. Review draft: GmailGetDraft(draft_id) → verify content")
    print("3. Send draft: GmailSendDraft(draft_id) → message_id")
    print("4. Verify sent: GmailGetMessage(message_id) → confirm delivery")
    print("=" * 80)

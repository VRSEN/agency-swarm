#!/usr/bin/env python3
import json
import os
import requests

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailAddLabel(BaseTool):
    """
    Add labels to a Gmail message (similar to folders/tags in other email systems).

    Common use cases:
    - Organize emails by adding custom labels (e.g., "Label_123", "Label_ProjectX")
    - Flag important messages: add_label_ids=["IMPORTANT"]
    - Star messages: add_label_ids=["STARRED"]
    - Mark as unread: add_label_ids=["UNREAD"]
    - Move to inbox: add_label_ids=["INBOX"]

    System Labels (built-in):
    - "IMPORTANT" - Mark as important
    - "STARRED" - Star the message
    - "UNREAD" - Mark as unread
    - "INBOX" - Move to inbox
    - "SENT" - Move to sent
    - "DRAFT" - Mark as draft
    - "SPAM" - Mark as spam
    - "TRASH" - Move to trash

    Custom Labels:
    - Use format "Label_123" (get IDs from GmailListLabels tool)
    - Create new labels with GmailCreateLabel tool first

    Note: To remove labels, use GmailRemoveLabel tool instead.
    For batch operations on multiple messages, use GmailBatchModifyMessages.
    """

    message_id: str = Field(
        ...,
        description="Gmail message ID (required). Example: '18c2f3a1b4e5d6f7'"
    )

    label_ids: list = Field(
        ...,
        description="List of label IDs to add (required). Examples: ['IMPORTANT'], ['Label_123', 'STARRED'], ['INBOX']"
    )

    def run(self):
        """
        Executes GMAIL_ADD_LABEL_TO_EMAIL via Composio SDK.
        Returns JSON string with success status and updated labels.
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        connection_id = os.getenv("GMAIL_CONNECTION_ID")

        if not api_key or not connection_id:
            return json.dumps({
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env"
            })

        try:
            # Validate inputs
            if not self.message_id:
                return json.dumps({
                    "error": "message_id is required"
                })

            if not self.label_ids or len(self.label_ids) == 0:
                return json.dumps({
                    "error": "label_ids is required and must contain at least one label ID"
                })            # Prepare parameters for adding labels
            params = {
                "message_id": self.message_id,
                "label_ids": self.label_ids,
                "user_id": "me"
            }

            # Execute Gmail add label via Composio
            # Prepare API request
            url = "https://backend.composio.dev/api/v2/actions/GMAIL_ADD_LABEL_TO_EMAIL/execute"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "connectedAccountId": connection_id,
                "input": params
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
                    "message_id": self.message_id,
                    "labels_added": self.label_ids,
                    "current_labels": data.get("labelIds", []),
                    "thread_id": data.get("threadId"),
                    "message": f"Successfully added {len(self.label_ids)} label(s) to message"
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "message": "Failed to add labels to message"
                }, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "error": f"API request failed: {str(e)}",


                "type": "RequestException"
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "error": f"Error adding labels: {str(e)}",
                "type": type(e).__name__
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailAddLabel...")

    # Test 1: Add IMPORTANT label
    print("\n1. Add IMPORTANT label:")
    tool = GmailAddLabel(
        message_id="18c2f3a1b4e5d6f7",
        label_ids=["IMPORTANT"]
    )
    result = tool.run()
    print(result)

    # Test 2: Add STARRED label
    print("\n2. Add STARRED label:")
    tool = GmailAddLabel(
        message_id="18c2f3a1b4e5d6f7",
        label_ids=["STARRED"]
    )
    result = tool.run()
    print(result)

    # Test 3: Add custom label
    print("\n3. Add custom label:")
    tool = GmailAddLabel(
        message_id="18c2f3a1b4e5d6f7",
        label_ids=["Label_123"]
    )
    result = tool.run()
    print(result)

    # Test 4: Add multiple labels at once
    print("\n4. Add multiple labels:")
    tool = GmailAddLabel(
        message_id="18c2f3a1b4e5d6f7",
        label_ids=["IMPORTANT", "STARRED", "Label_ProjectX"]
    )
    result = tool.run()
    print(result)

    # Test 5: Mark as unread
    print("\n5. Mark as unread (add UNREAD label):")
    tool = GmailAddLabel(
        message_id="18c2f3a1b4e5d6f7",
        label_ids=["UNREAD"]
    )
    result = tool.run()
    print(result)

    # Test 6: Move to inbox
    print("\n6. Move to inbox (add INBOX label):")
    tool = GmailAddLabel(
        message_id="18c2f3a1b4e5d6f7",
        label_ids=["INBOX"]
    )
    result = tool.run()
    print(result)

    # Test 7: Missing message_id (should error)
    print("\n7. Test with missing message_id (should error):")
    tool = GmailAddLabel(
        message_id="",
        label_ids=["IMPORTANT"]
    )
    result = tool.run()
    print(result)

    # Test 8: Empty label_ids (should error)
    print("\n8. Test with empty label_ids (should error):")
    tool = GmailAddLabel(
        message_id="18c2f3a1b4e5d6f7",
        label_ids=[]
    )
    result = tool.run()
    print(result)

    # Test 9: Add category labels
    print("\n9. Add category labels:")
    tool = GmailAddLabel(
        message_id="18c2f3a1b4e5d6f7",
        label_ids=["CATEGORY_SOCIAL"]
    )
    result = tool.run()
    print(result)

    # Test 10: Add work label
    print("\n10. Add work label:")
    tool = GmailAddLabel(
        message_id="18c2f3a1b4e5d6f7",
        label_ids=["Label_Work"]
    )
    result = tool.run()
    print(result)

    print("\nTest completed!")
    print("\nCommon Gmail Label IDs:")
    print("\nSystem Labels:")
    print("- INBOX: Messages in inbox")
    print("- UNREAD: Unread messages")
    print("- STARRED: Starred messages")
    print("- IMPORTANT: Important messages")
    print("- SENT: Sent messages")
    print("- DRAFT: Draft messages")
    print("- SPAM: Spam messages")
    print("- TRASH: Trashed messages")
    print("\nCategory Labels:")
    print("- CATEGORY_PERSONAL: Personal category")
    print("- CATEGORY_SOCIAL: Social category")
    print("- CATEGORY_PROMOTIONS: Promotions category")
    print("- CATEGORY_UPDATES: Updates category")
    print("- CATEGORY_FORUMS: Forums category")
    print("\nCustom Labels:")
    print("- Label_123: Custom label (get ID from GmailListLabels)")
    print("- Create new labels with GmailCreateLabel tool")
    print("\nProduction usage:")
    print("- Requires valid Composio API key and Gmail entity ID")
    print("- Message ID must be valid Gmail message ID")
    print("- Label IDs are case-sensitive")
    print("- System labels use UPPERCASE format")
    print("- Custom labels use 'Label_' prefix format")
    print("\nRelated Tools:")
    print("- GmailListLabels: List all available labels")
    print("- GmailCreateLabel: Create new custom labels")
    print("- GmailRemoveLabel: Remove labels from messages")
    print("- GmailBatchModifyMessages: Add/remove labels on multiple messages")

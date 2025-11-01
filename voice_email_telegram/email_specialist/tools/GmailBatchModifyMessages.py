#!/usr/bin/env python3
import json
import os

from composio import Composio
from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailBatchModifyMessages(BaseTool):
    """
    Batch modify Gmail messages: mark as read/unread, archive, star, and organize.

    Common use cases:
    - Mark as read: remove_label_ids=["UNREAD"]
    - Mark as unread: add_label_ids=["UNREAD"]
    - Archive: remove_label_ids=["INBOX"]
    - Unarchive: add_label_ids=["INBOX"]
    - Star: add_label_ids=["STARRED"]
    - Unstar: remove_label_ids=["STARRED"]
    - Mark as important: add_label_ids=["IMPORTANT"]
    - Remove importance: remove_label_ids=["IMPORTANT"]

    Supports batch operations on multiple messages at once.
    """

    message_ids: list = Field(
        ...,
        description="List of Gmail message IDs to modify (required). Example: ['msg_123', 'msg_456']"
    )

    add_label_ids: list = Field(
        default=[],
        description="List of label IDs to add. Common: ['STARRED', 'UNREAD', 'IMPORTANT', 'INBOX']"
    )

    remove_label_ids: list = Field(
        default=[],
        description="List of label IDs to remove. Common: ['UNREAD', 'INBOX', 'STARRED', 'IMPORTANT']"
    )

    def run(self):
        """
        Executes GMAIL_BATCH_MODIFY_MESSAGES via Composio SDK.
        Returns JSON string with success status and modified message count.
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
            if not self.message_ids or len(self.message_ids) == 0:
                return json.dumps({
                    "error": "message_ids is required and must contain at least one message ID"
                })

            if not self.add_label_ids and not self.remove_label_ids:
                return json.dumps({
                    "error": "At least one of add_label_ids or remove_label_ids must be provided"
                })

            # Initialize Composio client
            client = Composio(api_key=api_key)

            # Prepare batch modify parameters
            params = {
                "message_ids": self.message_ids,
                "user_id": "me"
            }

            # Add label modifications if provided
            if self.add_label_ids:
                params["add_label_ids"] = self.add_label_ids

            if self.remove_label_ids:
                params["remove_label_ids"] = self.remove_label_ids

            # Execute Gmail batch modify via Composio
            result = client.tools.execute(
                "GMAIL_BATCH_MODIFY_MESSAGES",
                params,
                user_id=entity_id
            )

            # Format response
            if result.get("successful"):
                # Build operation summary
                operations = []
                if self.add_label_ids:
                    operations.append(f"Added labels: {', '.join(self.add_label_ids)}")
                if self.remove_label_ids:
                    operations.append(f"Removed labels: {', '.join(self.remove_label_ids)}")

                return json.dumps({
                    "success": True,
                    "modified_count": len(self.message_ids),
                    "message_ids": self.message_ids,
                    "operations": operations,
                    "add_label_ids": self.add_label_ids,
                    "remove_label_ids": self.remove_label_ids,
                    "message": f"Successfully modified {len(self.message_ids)} message(s)"
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "message": "Failed to modify messages"
                }, indent=2)

        except Exception as e:
            return json.dumps({
                "error": f"Error modifying messages: {str(e)}",
                "type": type(e).__name__
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailBatchModifyMessages...")

    # Test 1: Mark messages as read
    print("\n1. Mark messages as read:")
    tool = GmailBatchModifyMessages(
        message_ids=["msg_123", "msg_456"],
        remove_label_ids=["UNREAD"]
    )
    result = tool.run()
    print(result)

    # Test 2: Mark messages as unread
    print("\n2. Mark messages as unread:")
    tool = GmailBatchModifyMessages(
        message_ids=["msg_789"],
        add_label_ids=["UNREAD"]
    )
    result = tool.run()
    print(result)

    # Test 3: Archive messages (remove from inbox)
    print("\n3. Archive messages:")
    tool = GmailBatchModifyMessages(
        message_ids=["msg_111", "msg_222", "msg_333"],
        remove_label_ids=["INBOX"]
    )
    result = tool.run()
    print(result)

    # Test 4: Unarchive messages (add back to inbox)
    print("\n4. Unarchive messages:")
    tool = GmailBatchModifyMessages(
        message_ids=["msg_444"],
        add_label_ids=["INBOX"]
    )
    result = tool.run()
    print(result)

    # Test 5: Star messages
    print("\n5. Star messages:")
    tool = GmailBatchModifyMessages(
        message_ids=["msg_555", "msg_666"],
        add_label_ids=["STARRED"]
    )
    result = tool.run()
    print(result)

    # Test 6: Unstar messages
    print("\n6. Unstar messages:")
    tool = GmailBatchModifyMessages(
        message_ids=["msg_777"],
        remove_label_ids=["STARRED"]
    )
    result = tool.run()
    print(result)

    # Test 7: Mark as important
    print("\n7. Mark as important:")
    tool = GmailBatchModifyMessages(
        message_ids=["msg_888"],
        add_label_ids=["IMPORTANT"]
    )
    result = tool.run()
    print(result)

    # Test 8: Archive and mark as read (combine operations)
    print("\n8. Archive and mark as read:")
    tool = GmailBatchModifyMessages(
        message_ids=["msg_999"],
        remove_label_ids=["INBOX", "UNREAD"]
    )
    result = tool.run()
    print(result)

    # Test 9: Star and mark as unread
    print("\n9. Star and mark as unread:")
    tool = GmailBatchModifyMessages(
        message_ids=["msg_1010"],
        add_label_ids=["STARRED", "UNREAD"]
    )
    result = tool.run()
    print(result)

    # Test 10: Missing message_ids (should error)
    print("\n10. Test with missing message_ids (should error):")
    tool = GmailBatchModifyMessages(
        message_ids=[],
        remove_label_ids=["UNREAD"]
    )
    result = tool.run()
    print(result)

    # Test 11: No label modifications (should error)
    print("\n11. Test with no label modifications (should error):")
    tool = GmailBatchModifyMessages(
        message_ids=["msg_123"]
    )
    result = tool.run()
    print(result)

    # Test 12: Batch operation on many messages
    print("\n12. Batch archive 10 messages:")
    tool = GmailBatchModifyMessages(
        message_ids=[f"msg_{i}" for i in range(1, 11)],
        remove_label_ids=["INBOX", "UNREAD"]
    )
    result = tool.run()
    print(result)

    print("\nTest completed!")
    print("\nCommon Gmail Label IDs:")
    print("- INBOX: Messages in inbox")
    print("- UNREAD: Unread messages")
    print("- STARRED: Starred messages")
    print("- IMPORTANT: Important messages")
    print("- SENT: Sent messages")
    print("- DRAFT: Draft messages")
    print("- SPAM: Spam messages")
    print("- TRASH: Trashed messages")
    print("\nProduction usage:")
    print("- Requires valid Composio API key and Gmail entity ID")
    print("- Message IDs must be valid Gmail message IDs")
    print("- Label IDs are case-sensitive")
    print("- Can combine multiple add/remove operations in one call")

#!/usr/bin/env python3
import json
import os

from composio import Composio
from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailModifyThreadLabels(BaseTool):
    """
    Modify labels for an entire Gmail thread (conversation) - adds or removes labels from ALL messages in the thread.

    KEY DIFFERENCE from GmailAddLabel:
    - GmailAddLabel: Modifies a SINGLE message
    - GmailModifyThreadLabels: Modifies ALL messages in a thread/conversation

    Common use cases:
    - "Archive this entire conversation" - remove_label_ids=["INBOX"]
    - "Mark whole thread as important" - add_label_ids=["IMPORTANT"]
    - "Star the entire conversation" - add_label_ids=["STARRED"]
    - "Move thread to trash" - remove_label_ids=["INBOX"], add_label_ids=["TRASH"]
    - "Label entire project discussion" - add_label_ids=["Label_ProjectX"]

    System Labels (built-in):
    - "IMPORTANT" - Mark as important
    - "STARRED" - Star the thread
    - "UNREAD" - Mark as unread
    - "INBOX" - Keep in inbox
    - "SENT" - Move to sent
    - "DRAFT" - Mark as draft
    - "SPAM" - Mark as spam
    - "TRASH" - Move to trash

    Custom Labels:
    - Use format "Label_123" (get IDs from GmailListLabels tool)
    - Create new labels with GmailCreateLabel tool first

    Thread Operations:
    - Archive: remove_label_ids=["INBOX"]
    - Unarchive: add_label_ids=["INBOX"]
    - Star thread: add_label_ids=["STARRED"]
    - Unstar thread: remove_label_ids=["STARRED"]
    - Mark important: add_label_ids=["IMPORTANT"]
    - Mark unimportant: remove_label_ids=["IMPORTANT"]

    Note: For single messages, use GmailAddLabel or GmailRemoveLabel instead.
    For batch operations on multiple threads, consider using GmailBatchModifyMessages.
    """

    thread_id: str = Field(
        ...,
        description="Gmail thread ID (required). Example: '18c2f3a1b4e5d6f7'. Get thread IDs from GmailListThreads or GmailFetchEmails."
    )

    add_label_ids: list = Field(
        default=[],
        description="List of label IDs to ADD to all messages in thread. Examples: ['IMPORTANT'], ['Label_123', 'STARRED'], ['INBOX']"
    )

    remove_label_ids: list = Field(
        default=[],
        description="List of label IDs to REMOVE from all messages in thread. Examples: ['INBOX'] (archive), ['UNREAD'] (mark read), ['STARRED'] (unstar)"
    )

    def run(self):
        """
        Executes GMAIL_MODIFY_THREAD_LABELS via Composio SDK.
        Returns JSON string with success status, thread_id, and count of modified messages.
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
            if not self.thread_id:
                return json.dumps({
                    "error": "thread_id is required"
                })

            # At least one operation must be specified
            if not self.add_label_ids and not self.remove_label_ids:
                return json.dumps({
                    "error": "Must specify at least one of: add_label_ids or remove_label_ids"
                })

            # Initialize Composio client
            client = Composio(api_key=api_key)

            # Prepare parameters for modifying thread labels
            params = {
                "thread_id": self.thread_id,
                "user_id": "me"
            }

            # Add label operations if specified
            if self.add_label_ids:
                params["add_label_ids"] = self.add_label_ids

            if self.remove_label_ids:
                params["remove_label_ids"] = self.remove_label_ids

            # Execute Gmail modify thread labels via Composio
            result = client.tools.execute(
                "GMAIL_MODIFY_THREAD_LABELS",
                params,
                user_id=entity_id
            )

            # Format response
            if result.get("successful"):
                data = result.get("data", {})

                # Count modified messages (if available)
                modified_count = len(data.get("messages", [])) if "messages" in data else "unknown"

                response = {
                    "success": True,
                    "thread_id": self.thread_id,
                    "modified_message_count": modified_count,
                    "operations": []
                }

                # Add operation details
                if self.add_label_ids:
                    response["operations"].append({
                        "action": "add",
                        "labels": self.add_label_ids,
                        "count": len(self.add_label_ids)
                    })

                if self.remove_label_ids:
                    response["operations"].append({
                        "action": "remove",
                        "labels": self.remove_label_ids,
                        "count": len(self.remove_label_ids)
                    })

                # Add human-readable message
                operations_text = []
                if self.add_label_ids:
                    operations_text.append(f"added {len(self.add_label_ids)} label(s)")
                if self.remove_label_ids:
                    operations_text.append(f"removed {len(self.remove_label_ids)} label(s)")

                response["message"] = f"Successfully {' and '.join(operations_text)} to/from thread"

                # Add current labels if available
                if "labelIds" in data:
                    response["current_labels"] = data.get("labelIds", [])

                return json.dumps(response, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "message": "Failed to modify thread labels"
                }, indent=2)

        except Exception as e:
            return json.dumps({
                "error": f"Error modifying thread labels: {str(e)}",
                "type": type(e).__name__
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailModifyThreadLabels...")
    print("=" * 60)

    # Test 1: Archive entire thread (remove from inbox)
    print("\n1. Archive entire thread (remove INBOX label):")
    tool = GmailModifyThreadLabels(
        thread_id="18c2f3a1b4e5d6f7",
        remove_label_ids=["INBOX"]
    )
    result = tool.run()
    print(result)

    # Test 2: Star entire conversation
    print("\n2. Star entire conversation:")
    tool = GmailModifyThreadLabels(
        thread_id="18c2f3a1b4e5d6f7",
        add_label_ids=["STARRED"]
    )
    result = tool.run()
    print(result)

    # Test 3: Mark entire thread as important
    print("\n3. Mark entire thread as important:")
    tool = GmailModifyThreadLabels(
        thread_id="18c2f3a1b4e5d6f7",
        add_label_ids=["IMPORTANT"]
    )
    result = tool.run()
    print(result)

    # Test 4: Mark entire thread as read (remove UNREAD)
    print("\n4. Mark entire thread as read:")
    tool = GmailModifyThreadLabels(
        thread_id="18c2f3a1b4e5d6f7",
        remove_label_ids=["UNREAD"]
    )
    result = tool.run()
    print(result)

    # Test 5: Move thread back to inbox (unarchive)
    print("\n5. Unarchive thread (add INBOX label):")
    tool = GmailModifyThreadLabels(
        thread_id="18c2f3a1b4e5d6f7",
        add_label_ids=["INBOX"]
    )
    result = tool.run()
    print(result)

    # Test 6: Add custom project label to entire conversation
    print("\n6. Label entire conversation with custom label:")
    tool = GmailModifyThreadLabels(
        thread_id="18c2f3a1b4e5d6f7",
        add_label_ids=["Label_ProjectX"]
    )
    result = tool.run()
    print(result)

    # Test 7: Multiple operations - star and mark important
    print("\n7. Star and mark important:")
    tool = GmailModifyThreadLabels(
        thread_id="18c2f3a1b4e5d6f7",
        add_label_ids=["STARRED", "IMPORTANT"]
    )
    result = tool.run()
    print(result)

    # Test 8: Organize thread - archive and add custom label
    print("\n8. Archive and add custom label:")
    tool = GmailModifyThreadLabels(
        thread_id="18c2f3a1b4e5d6f7",
        add_label_ids=["Label_Archive2024"],
        remove_label_ids=["INBOX"]
    )
    result = tool.run()
    print(result)

    # Test 9: Move thread to trash
    print("\n9. Move thread to trash:")
    tool = GmailModifyThreadLabels(
        thread_id="18c2f3a1b4e5d6f7",
        add_label_ids=["TRASH"],
        remove_label_ids=["INBOX"]
    )
    result = tool.run()
    print(result)

    # Test 10: Unstar and mark unimportant
    print("\n10. Unstar and mark unimportant:")
    tool = GmailModifyThreadLabels(
        thread_id="18c2f3a1b4e5d6f7",
        remove_label_ids=["STARRED", "IMPORTANT"]
    )
    result = tool.run()
    print(result)

    # Test 11: Missing thread_id (should error)
    print("\n11. Test with missing thread_id (should error):")
    tool = GmailModifyThreadLabels(
        thread_id="",
        add_label_ids=["IMPORTANT"]
    )
    result = tool.run()
    print(result)

    # Test 12: No operations specified (should error)
    print("\n12. Test with no operations (should error):")
    tool = GmailModifyThreadLabels(
        thread_id="18c2f3a1b4e5d6f7"
    )
    result = tool.run()
    print(result)

    # Test 13: Complex workflow - organize project thread
    print("\n13. Complex workflow - organize project thread:")
    tool = GmailModifyThreadLabels(
        thread_id="18c2f3a1b4e5d6f7",
        add_label_ids=["Label_ProjectAlpha", "IMPORTANT", "STARRED"],
        remove_label_ids=["UNREAD"]
    )
    result = tool.run()
    print(result)

    print("\n" + "=" * 60)
    print("Test completed!")
    print("\n" + "=" * 60)
    print("\nGmailModifyThreadLabels vs GmailAddLabel:")
    print("-" * 60)
    print("GmailAddLabel:")
    print("  - Operates on: SINGLE MESSAGE")
    print("  - Use case: 'Label this email'")
    print("  - Scope: One message only")
    print()
    print("GmailModifyThreadLabels:")
    print("  - Operates on: ENTIRE THREAD (all messages)")
    print("  - Use case: 'Label this entire conversation'")
    print("  - Scope: All messages in the thread")
    print()
    print("=" * 60)
    print("\nCommon Thread Operations:")
    print("-" * 60)
    print("\nArchive Thread:")
    print("  remove_label_ids=['INBOX']")
    print()
    print("Unarchive Thread:")
    print("  add_label_ids=['INBOX']")
    print()
    print("Star Entire Conversation:")
    print("  add_label_ids=['STARRED']")
    print()
    print("Mark Thread as Read:")
    print("  remove_label_ids=['UNREAD']")
    print()
    print("Mark Thread as Important:")
    print("  add_label_ids=['IMPORTANT']")
    print()
    print("Organize Project Thread:")
    print("  add_label_ids=['Label_ProjectX', 'IMPORTANT']")
    print("  remove_label_ids=['INBOX']")
    print()
    print("Move Thread to Trash:")
    print("  add_label_ids=['TRASH']")
    print("  remove_label_ids=['INBOX']")
    print()
    print("=" * 60)
    print("\nSystem Labels:")
    print("-" * 60)
    print("- INBOX: Messages in inbox")
    print("- UNREAD: Unread messages")
    print("- STARRED: Starred messages")
    print("- IMPORTANT: Important messages")
    print("- SENT: Sent messages")
    print("- DRAFT: Draft messages")
    print("- SPAM: Spam messages")
    print("- TRASH: Trashed messages")
    print()
    print("Category Labels:")
    print("- CATEGORY_PERSONAL: Personal category")
    print("- CATEGORY_SOCIAL: Social category")
    print("- CATEGORY_PROMOTIONS: Promotions category")
    print("- CATEGORY_UPDATES: Updates category")
    print("- CATEGORY_FORUMS: Forums category")
    print()
    print("Custom Labels:")
    print("- Label_123: Custom label (get ID from GmailListLabels)")
    print("- Create new labels with GmailCreateLabel tool")
    print()
    print("=" * 60)
    print("\nProduction Usage:")
    print("-" * 60)
    print("- Requires valid Composio API key and Gmail entity ID")
    print("- Thread ID must be valid Gmail thread ID")
    print("- Label IDs are case-sensitive")
    print("- System labels use UPPERCASE format")
    print("- Custom labels use 'Label_' prefix format")
    print("- At least one operation (add or remove) must be specified")
    print()
    print("=" * 60)
    print("\nRelated Tools:")
    print("-" * 60)
    print("- GmailListThreads: List all threads")
    print("- GmailFetchMessageByThreadId: Get thread details")
    print("- GmailListLabels: List all available labels")
    print("- GmailCreateLabel: Create new custom labels")
    print("- GmailAddLabel: Add label to SINGLE message")
    print("- GmailRemoveLabel: Remove label from SINGLE message")
    print("- GmailBatchModifyMessages: Modify multiple individual messages")

#!/usr/bin/env python3
"""
GmailListLabels Tool - Lists all Gmail labels (system and custom) using Composio SDK.

Based on validated pattern from FINAL_VALIDATION_SUMMARY.md
Uses Composio SDK client.tools.execute() with GMAIL_LIST_LABELS action.
"""
import json
import os
import requests

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailListLabels(BaseTool):
    """
    Lists all Gmail labels including both system labels and user-created custom labels.

    System labels include:
    - INBOX, SENT, DRAFT, TRASH, SPAM
    - UNREAD, STARRED, IMPORTANT
    - CATEGORY_PERSONAL, CATEGORY_SOCIAL, CATEGORY_PROMOTIONS, etc.

    Custom labels are user-created organizational labels.

    Use cases:
    - Get label IDs for use with GmailAddLabel tool
    - Show user their custom labels
    - "What labels do I have?"
    - "List my Gmail labels"
    """

    # No parameters required - lists all labels for the authenticated user
    user_id: str = Field(
        default="me",
        description="Gmail user ID. Always 'me' for the authenticated user."
    )

    def run(self):
        """
        Executes GMAIL_LIST_LABELS via Composio SDK.

        Returns:
            JSON string with:
            - success: bool - Whether fetch was successful
            - count: int - Number of labels found
            - labels: list - Array of label objects with:
                - id: Label ID (use with GmailAddLabel)
                - name: Label display name
                - type: "system" or "user"
                - messagesTotal: Total messages with this label
                - messagesUnread: Unread messages with this label
            - system_labels: list - System labels only
            - custom_labels: list - User-created labels only
            - error: str - Error message if failed
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        connection_id = os.getenv("GMAIL_CONNECTION_ID")

        if not api_key or not connection_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env",
                "count": 0,
                "labels": [],
                "system_labels": [],
                "custom_labels": []
            }, indent=2)

        try:            # Execute GMAIL_LIST_LABELS via Composio
            # Prepare API request
            url = "https://backend.composio.dev/api/v2/actions/GMAIL_LIST_LABELS/execute"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "connectedAccountId": connection_id,
                "input": {
                    "user_id": self.user_id  # "me" for authenticated user
                }
            }

            # Execute via Composio REST API
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()

            # Extract labels from response
            labels = result.get("data", {}).get("labels", [])

            # Separate system and custom labels
            system_labels = [
                label for label in labels
                if label.get("type") == "system"
            ]

            custom_labels = [
                label for label in labels
                if label.get("type") == "user"
            ]

            # Format successful response
            return json.dumps({
                "success": True,
                "count": len(labels),
                "labels": labels,
                "system_labels": system_labels,
                "custom_labels": custom_labels,
                "system_count": len(system_labels),
                "custom_count": len(custom_labels)
            }, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "error": f"API request failed: {str(e)}",


                "type": "RequestException"
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error listing labels: {str(e)}",
                "type": type(e).__name__,
                "count": 0,
                "labels": [],
                "system_labels": [],
                "custom_labels": []
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailListLabels...")
    print("=" * 60)

    # Test 1: List all labels
    print("\n1. List all Gmail labels:")
    tool = GmailListLabels()
    result = tool.run()
    print(result)

    # Parse result to show label structure
    try:
        result_data = json.loads(result)
        if result_data.get("success"):
            print("\n" + "=" * 60)
            print("LABEL SUMMARY:")
            print(f"Total labels: {result_data.get('count', 0)}")
            print(f"System labels: {result_data.get('system_count', 0)}")
            print(f"Custom labels: {result_data.get('custom_count', 0)}")

            # Show system labels
            print("\nSYSTEM LABELS:")
            for label in result_data.get("system_labels", [])[:10]:
                print(f"  - {label.get('name')} (ID: {label.get('id')})")
                if label.get('messagesTotal'):
                    print(f"    Messages: {label.get('messagesTotal')} total, {label.get('messagesUnread', 0)} unread")

            # Show custom labels
            if result_data.get("custom_labels"):
                print("\nCUSTOM LABELS:")
                for label in result_data.get("custom_labels", []):
                    print(f"  - {label.get('name')} (ID: {label.get('id')})")
                    if label.get('messagesTotal'):
                        print(f"    Messages: {label.get('messagesTotal')} total, {label.get('messagesUnread', 0)} unread")
            else:
                print("\nNo custom labels found.")

    except json.JSONDecodeError:
        print("Could not parse result for summary display")

    print("\n" + "=" * 60)
    print("Test completed!")
    print("\nUsage Examples:")
    print("- 'What labels do I have?' - Lists all labels")
    print("- 'Show me my custom labels' - Lists user-created labels")
    print("- 'How many unread emails in my Inbox?' - Check INBOX label stats")
    print("\nIntegration:")
    print("- Use label IDs with GmailAddLabel tool")
    print("- Use label IDs with GmailFetchEmails (query='label:LABELNAME')")
    print("\nProduction Requirements:")
    print("- Set COMPOSIO_API_KEY in .env")
    print("- Set GMAIL_CONNECTION_ID in .env")
    print("- Gmail account connected via Composio")

"""
RubeMCPClient - Dynamic tool execution via Composio Rube MCP Server

This tool replaces 25+ static Gmail tool files by connecting to Rube MCP server
for dynamic tool execution. Rube provides 500+ tools including Gmail, Slack, etc.

Usage:
    tool = RubeMCPClient(
        action="gmail_send_email",
        params={"to": "user@example.com", "subject": "Hello", "body": "Test"}
    )
    result = tool.run()
"""

import json
import os
from typing import Any, Dict, Optional

import requests
from pydantic import Field

from agency_swarm.tools import BaseTool


class RubeMCPClient(BaseTool):
    """
    Executes actions dynamically via Composio Rube MCP Server.

    Replaces 25+ individual Gmail tool files with a single dynamic client.
    Supports 500+ apps including Gmail, Slack, GitHub, Notion, etc.

    Benefits:
    - Fast startup (<5s vs 3+ min)
    - Dynamic tool loading (no pre-loading)
    - Single source of truth
    - Auto-updated tools via Rube
    """

    action: str = Field(
        ...,
        description="""The action to execute. Examples:

        Gmail Actions:
        - gmail_send_email: Send an email
        - gmail_fetch_emails: Search/fetch emails
        - gmail_create_draft: Create email draft
        - gmail_get_message: Get email details
        - gmail_add_label: Add label to email
        - gmail_list_labels: List all labels
        - gmail_move_to_trash: Move email to trash
        - gmail_get_profile: Get Gmail profile

        Other Apps (examples):
        - slack_send_message: Send Slack message
        - github_create_issue: Create GitHub issue
        - notion_create_page: Create Notion page

        For full list, see: https://rube.app/tools
        """,
        min_length=1,
    )

    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="""Parameters for the action as a dictionary.

        Examples:

        gmail_send_email:
            {"to": "user@example.com", "subject": "Hello", "body": "Message", "cc": [], "bcc": []}

        gmail_fetch_emails:
            {"query": "is:unread", "max_results": 10}

        gmail_create_draft:
            {"to": "user@example.com", "subject": "Draft", "body": "Content"}

        gmail_get_message:
            {"message_id": "abc123xyz"}
        """,
    )

    def run(self) -> str:
        """
        Execute action via Rube MCP server.

        Returns:
            JSON string with result or error
        """
        # Get credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        connection_id = os.getenv("GMAIL_CONNECTION_ID")

        if not api_key:
            return json.dumps({
                "success": False,
                "error": "COMPOSIO_API_KEY not found in environment"
            }, indent=2)

        if not connection_id:
            return json.dumps({
                "success": False,
                "error": "GMAIL_CONNECTION_ID not found in environment"
            }, indent=2)

        try:
            # Convert action name to Composio format (e.g., gmail_send_email -> GMAIL_SEND_EMAIL)
            composio_action = self.action.upper()

            # Call Composio REST API (Rube backend)
            url = f"https://backend.composio.dev/api/v2/actions/{composio_action}/execute"

            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }

            payload = {
                "connectedAccountId": connection_id,
                "input": self.params
            }

            response = requests.post(url, headers=headers, json=payload, timeout=30)

            if response.status_code == 200:
                result = response.json()
                return json.dumps({
                    "success": True,
                    "action": self.action,
                    "data": result
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "action": self.action,
                    "error": f"HTTP {response.status_code}: {response.text}"
                }, indent=2)

        except requests.exceptions.Timeout:
            return json.dumps({
                "success": False,
                "action": self.action,
                "error": "Request timeout after 30 seconds"
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "success": False,
                "action": self.action,
                "error": f"{type(e).__name__}: {str(e)}"
            }, indent=2)


if __name__ == "__main__":
    # Test the tool
    print("Testing RubeMCPClient...\n")
    print("=" * 80)

    # Test 1: Gmail fetch emails
    print("\nTest 1: Fetch unread emails")
    print("-" * 80)
    tool = RubeMCPClient(
        action="gmail_fetch_emails",
        params={"query": "is:unread", "max_results": 5}
    )
    result = tool.run()
    print(result)

    # Test 2: Gmail get profile
    print("\n\nTest 2: Get Gmail profile")
    print("-" * 80)
    tool = RubeMCPClient(
        action="gmail_get_profile",
        params={}
    )
    result = tool.run()
    print(result)

    print("\n" + "=" * 80)
    print("Tests complete!")

#!/usr/bin/env python3
"""
GmailFetchEmails Tool - Fetches Gmail emails using Composio REST API.

UPDATED: Uses Composio REST API directly instead of SDK (SDK has compatibility issues).
This approach matches the working Rube MCP implementation.
"""
import json
import os
import requests

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailFetchEmails(BaseTool):
    """
    Fetches Gmail emails using Composio SDK with advanced search capabilities.

    Supports Gmail search operators:
    - from:sender@email.com - Emails from specific sender
    - to:recipient@email.com - Emails to specific recipient
    - subject:keyword - Emails with keyword in subject
    - is:unread - Unread emails only
    - is:read - Read emails only
    - is:starred - Starred emails
    - has:attachment - Emails with attachments
    - label:labelname - Emails with specific label
    - after:YYYY/MM/DD - Emails after date
    - before:YYYY/MM/DD - Emails before date
    - newer_than:2d - Emails newer than 2 days
    - older_than:1w - Emails older than 1 week

    Examples:
    - "from:john@example.com is:unread" - Unread emails from John
    - "subject:meeting" - All emails about meetings
    - "" - All recent emails (default)
    """

    query: str = Field(
        default="",
        description="Gmail search query using Gmail search operators (e.g., 'from:john@example.com is:unread', 'subject:meeting', 'has:attachment'). Empty string returns recent emails."
    )

    max_results: int = Field(
        default=10,
        description="Maximum number of emails to fetch (1-100). Default is 10."
    )

    def run(self):
        """
        Executes GMAIL_FETCH_EMAILS via Composio REST API.

        Returns:
            JSON string with:
            - success: bool - Whether fetch was successful
            - count: int - Number of emails fetched
            - messages: list - Array of email objects
            - query: str - Search query used
            - error: str - Error message if failed
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        entity_id = os.getenv("GMAIL_CONNECTION_ID")  # Use connection ID (ca_*) not entity ID

        if not api_key or not entity_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env",
                "count": 0,
                "messages": []
            }, indent=2)

        try:
            # Validate max_results range
            if self.max_results < 1 or self.max_results > 500:
                return json.dumps({
                    "success": False,
                    "error": "max_results must be between 1 and 500",
                    "count": 0,
                    "messages": []
                }, indent=2)

            # Prepare API request
            url = "https://backend.composio.dev/api/v2/actions/GMAIL_FETCH_EMAILS/execute"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "connectedAccountId": entity_id,
                "input": {
                    "query": self.query,
                    "max_results": self.max_results,
                    "user_id": "me",
                    "include_payload": True,
                    "verbose": True
                }
            }

            # Execute via Composio REST API
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()

            # Extract messages from response
            if result.get("successfull") or result.get("data"):
                messages = result.get("data", {}).get("messages", [])

                # Format successful response
                return json.dumps({
                    "success": True,
                    "count": len(messages),
                    "messages": messages,
                    "query": self.query if self.query else "all recent emails",
                    "max_results": self.max_results
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.get("error", "Unknown error from Composio API"),
                    "count": 0,
                    "messages": []
                }, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "success": False,
                "error": f"API request failed: {str(e)}",
                "type": "RequestException",
                "count": 0,
                "messages": [],
                "query": self.query
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailFetchEmails...")
    print("=" * 60)

    # Test 1: Fetch recent emails (default)
    print("\n1. Fetch recent emails (default query):")
    tool = GmailFetchEmails(max_results=5)
    result = tool.run()
    print(result)

    # Test 2: Fetch unread emails
    print("\n2. Fetch unread emails:")
    tool = GmailFetchEmails(query="is:unread", max_results=5)
    result = tool.run()
    print(result)

    # Test 3: Fetch emails from specific sender
    print("\n3. Fetch emails from specific sender:")
    tool = GmailFetchEmails(query="from:john@example.com", max_results=5)
    result = tool.run()
    print(result)

    # Test 4: Fetch emails with attachments
    print("\n4. Fetch emails with attachments:")
    tool = GmailFetchEmails(query="has:attachment", max_results=5)
    result = tool.run()
    print(result)

    # Test 5: Fetch starred emails
    print("\n5. Fetch starred emails:")
    tool = GmailFetchEmails(query="is:starred", max_results=3)
    result = tool.run()
    print(result)

    # Test 6: Complex search query
    print("\n6. Fetch unread emails from specific sender:")
    tool = GmailFetchEmails(query="from:boss@company.com is:unread", max_results=5)
    result = tool.run()
    print(result)

    # Test 7: Subject search
    print("\n7. Search emails by subject:")
    tool = GmailFetchEmails(query="subject:meeting", max_results=5)
    result = tool.run()
    print(result)

    # Test 8: Date range search
    print("\n8. Fetch emails from last 7 days:")
    tool = GmailFetchEmails(query="newer_than:7d", max_results=10)
    result = tool.run()
    print(result)

    # Test 9: Invalid max_results (should error)
    print("\n9. Test with invalid max_results (should error):")
    tool = GmailFetchEmails(max_results=150)
    result = tool.run()
    print(result)

    # Test 10: Combined filters
    print("\n10. Complex query with multiple filters:")
    tool = GmailFetchEmails(
        query="from:team@example.com has:attachment newer_than:3d",
        max_results=5
    )
    result = tool.run()
    print(result)

    print("\n" + "=" * 60)
    print("Test completed!")
    print("\nGmail Search Query Examples:")
    print("- 'from:sender@email.com' - Emails from specific sender")
    print("- 'to:recipient@email.com' - Emails to specific recipient")
    print("- 'subject:meeting' - Emails with 'meeting' in subject")
    print("- 'is:unread' - Unread emails only")
    print("- 'is:starred' - Starred emails")
    print("- 'has:attachment' - Emails with attachments")
    print("- 'label:important' - Emails with 'important' label")
    print("- 'newer_than:2d' - Emails from last 2 days")
    print("- 'from:john@example.com is:unread' - Combined filters")
    print("\nProduction Requirements:")
    print("- Set COMPOSIO_API_KEY in .env")
    print("- Set GMAIL_ENTITY_ID in .env")
    print("- Gmail account connected via Composio")

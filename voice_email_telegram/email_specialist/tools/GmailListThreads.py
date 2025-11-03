#!/usr/bin/env python3
"""
GmailListThreads.py - List email threads (conversations) with search capabilities

Purpose: List Gmail threads (conversations containing multiple messages) with optional search filtering.
A thread represents an email conversation that may contain multiple related messages.

UPDATED: Uses Composio REST API instead of SDK (SDK has compatibility issues).
"""
import json
import os
import requests

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailListThreads(BaseTool):
    """
    Lists Gmail email threads (conversations) with optional search filtering.

    A thread is an email conversation that may contain multiple messages.
    Each thread has a thread_id and contains one or more message IDs.
    Useful for viewing conversation history and organizing related emails.

    Examples:
    - List all threads: query=""
    - List unread threads: query="is:unread"
    - List threads from specific sender: query="from:john@example.com"
    - List threads about meetings: query="subject:meeting"
    """

    query: str = Field(
        default="",
        description="Gmail search query to filter threads (e.g., 'subject:meeting', 'from:john@example.com', 'is:unread'). Leave empty to list all threads."
    )

    max_results: int = Field(
        default=10,
        description="Maximum number of threads to return (1-100). Default is 10."
    )

    def run(self):
        """
        Executes GMAIL_LIST_THREADS via Composio REST API.

        Returns:
            JSON string containing:
            - success: bool - Whether the operation succeeded
            - count: int - Number of threads returned
            - threads: list - Array of thread objects with thread_id and message snippet
            - query: str - The search query used
        """
        # Get Composio credentials from environment
        api_key = os.getenv("COMPOSIO_API_KEY")
        entity_id = os.getenv("GMAIL_CONNECTION_ID")

        if not api_key or not entity_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env",
                "count": 0,
                "threads": []
            }, indent=2)

        try:
            # Validate max_results
            if self.max_results < 1 or self.max_results > 100:
                return json.dumps({
                    "success": False,
                    "error": "max_results must be between 1 and 100",
                    "count": 0,
                    "threads": []
                }, indent=2)

            # Prepare parameters for GMAIL_LIST_THREADS
            params = {
                "max_results": self.max_results,
                "user_id": "me"
            }

            # Add query if provided
            if self.query:
                params["query"] = self.query

            # Prepare API request
            url = "https://backend.composio.dev/api/v2/actions/GMAIL_LIST_THREADS/execute"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "connectedAccountId": entity_id,
                "input": params
            }

            # Execute via Composio REST API
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()

            # Extract threads from response
            if result.get("successfull") or result.get("data"):
                threads = result.get("data", {}).get("threads", [])

                # Format response
                return json.dumps({
                    "success": True,
                    "count": len(threads),
                    "threads": threads,
                    "query": self.query if self.query else "all threads",
                    "max_results": self.max_results
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "count": 0,
                    "threads": []
                }, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "success": False,
                "error": f"API request failed: {str(e)}",
                "type": "RequestException",
                "count": 0,
                "threads": []
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error listing threads: {str(e)}",
                "type": type(e).__name__,
                "count": 0,
                "threads": []
            }, indent=2)


if __name__ == "__main__":
    """
    Test suite for GmailListThreads tool.
    Tests various scenarios to ensure robust functionality.
    """
    print("=" * 60)
    print("Testing GmailListThreads Tool")
    print("=" * 60)

    # Test 1: List all threads (default)
    print("\n1. List all threads (default 10):")
    print("-" * 60)
    tool = GmailListThreads()
    result = tool.run()
    print(result)

    # Test 2: List unread threads
    print("\n2. List unread threads:")
    print("-" * 60)
    tool = GmailListThreads(query="is:unread")
    result = tool.run()
    print(result)

    # Test 3: List threads from specific sender
    print("\n3. List threads from specific sender:")
    print("-" * 60)
    tool = GmailListThreads(query="from:support@example.com")
    result = tool.run()
    print(result)

    # Test 4: List threads with subject filter
    print("\n4. List threads about meetings:")
    print("-" * 60)
    tool = GmailListThreads(query="subject:meeting")
    result = tool.run()
    print(result)

    # Test 5: List only 5 threads
    print("\n5. List only 5 threads:")
    print("-" * 60)
    tool = GmailListThreads(max_results=5)
    result = tool.run()
    print(result)

    # Test 6: List starred threads
    print("\n6. List starred threads:")
    print("-" * 60)
    tool = GmailListThreads(query="is:starred")
    result = tool.run()
    print(result)

    # Test 7: List threads in inbox
    print("\n7. List threads in inbox:")
    print("-" * 60)
    tool = GmailListThreads(query="in:inbox")
    result = tool.run()
    print(result)

    # Test 8: List threads with attachments
    print("\n8. List threads with attachments:")
    print("-" * 60)
    tool = GmailListThreads(query="has:attachment")
    result = tool.run()
    print(result)

    # Test 9: Invalid max_results (should error)
    print("\n9. Test invalid max_results (should error):")
    print("-" * 60)
    tool = GmailListThreads(max_results=150)  # Over 100 limit
    result = tool.run()
    print(result)

    # Test 10: Complex query
    print("\n10. Complex query (unread from specific sender):")
    print("-" * 60)
    tool = GmailListThreads(query="is:unread from:john@example.com")
    result = tool.run()
    print(result)

    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)
    print("\nThread vs Message:")
    print("- Thread = Email conversation (may contain multiple messages)")
    print("- Message = Individual email within a thread")
    print("- Each thread has thread_id and list of message IDs")
    print("\nCommon Gmail Search Queries:")
    print("- 'is:unread' - Unread threads")
    print("- 'is:starred' - Starred threads")
    print("- 'from:email@example.com' - From specific sender")
    print("- 'to:email@example.com' - To specific recipient")
    print("- 'subject:keyword' - Subject contains keyword")
    print("- 'has:attachment' - Threads with attachments")
    print("- 'in:inbox' - Threads in inbox")
    print("- 'is:important' - Important threads")
    print("- 'after:2024/11/01' - Threads after date")
    print("- 'before:2024/11/01' - Threads before date")
    print("\nProduction ready:")
    print("- Uses Composio REST API pattern")
    print("- Requires COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env")
    print("- Returns JSON with success, count, threads array")

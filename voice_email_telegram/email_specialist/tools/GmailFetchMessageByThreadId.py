#!/usr/bin/env python3
"""
GmailFetchMessageByThreadId Tool - Fetches all messages in a Gmail thread (conversation).

Based on validated pattern from FINAL_VALIDATION_SUMMARY.md
Uses Composio SDK client.tools.execute() with GMAIL_FETCH_MESSAGE_BY_THREAD_ID action.
"""
import json
import os
import requests

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailFetchMessageByThreadId(BaseTool):
    """
    Fetches all messages in a Gmail thread (email conversation) by thread ID.

    Use this tool when you need to:
    - Show the full conversation with someone
    - Read all messages in an email thread
    - Get the complete history of an email exchange
    - See all replies in a conversation

    Returns all messages in the thread in chronological order, including:
    - Original message
    - All replies
    - Forward history
    - Full message details (subject, sender, body, labels)

    Examples:
    - "Show me the full conversation with John"
    - "Read all messages in this thread"
    - "Get the complete email exchange about the project"
    """

    thread_id: str = Field(
        ...,
        description="Gmail thread ID (required). Example: '18c1234567890abcd'. This is the conversation ID that groups related emails together."
    )

    def run(self):
        """
        Executes GMAIL_FETCH_MESSAGE_BY_THREAD_ID via Composio SDK.

        Returns:
            JSON string with:
            - success: bool - Whether fetch was successful
            - thread_id: str - The thread ID requested
            - message_count: int - Number of messages in thread
            - messages: list - Array of all messages in chronological order
            - error: str - Error message if failed
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        connection_id = os.getenv("GMAIL_CONNECTION_ID")

        if not api_key or not connection_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env",
                "thread_id": self.thread_id,
                "message_count": 0,
                "messages": []
            }, indent=2)

        # Validate thread_id
        if not self.thread_id:
            return json.dumps({
                "success": False,
                "error": "thread_id is required",
                "message_count": 0,
                "messages": []
            }, indent=2)

        try:            # Execute GMAIL_FETCH_MESSAGE_BY_THREAD_ID via Composio
            # Prepare API request
            url = "https://backend.composio.dev/api/v2/actions/GMAIL_FETCH_MESSAGE_BY_THREAD_ID/execute"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "connectedAccountId": connection_id,
                "input": {
                    "thread_id": self.thread_id
                }
            }

            # Execute via Composio REST API
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()

            # Check if successful
            if result.get("successfull") or result.get("data"):
                thread_data = result.get("data", {})
                messages = thread_data.get("messages", [])

                # Extract key information from each message
                processed_messages = []
                for msg in messages:
                    headers = msg.get("payload", {}).get("headers", [])

                    # Helper function to get header value
                    def get_header(name):
                        for header in headers:
                            if header.get("name", "").lower() == name.lower():
                                return header.get("value", "")
                        return ""

                    # Extract body text
                    def get_body_text(payload):
                        """Recursively extract text from message payload."""
                        body_text = ""

                        # Check if this part has body data
                        if "body" in payload and "data" in payload["body"]:
                            return payload["body"]["data"]

                        # Check if this has parts (multipart message)
                        if "parts" in payload:
                            for part in payload["parts"]:
                                # Prefer text/plain over text/html
                                mime_type = part.get("mimeType", "")
                                if mime_type == "text/plain":
                                    if "body" in part and "data" in part["body"]:
                                        return part["body"]["data"]
                                # Fall back to HTML or recursive parts
                                body_text = get_body_text(part)
                                if body_text:
                                    return body_text

                        return body_text

                    payload = msg.get("payload", {})
                    body_data = get_body_text(payload)

                    # Build structured message object
                    processed_messages.append({
                        "message_id": msg.get("id"),
                        "thread_id": msg.get("threadId"),
                        "labels": msg.get("labelIds", []),
                        "snippet": msg.get("snippet", ""),
                        "subject": get_header("Subject"),
                        "from": get_header("From"),
                        "to": get_header("To"),
                        "cc": get_header("Cc"),
                        "date": get_header("Date"),
                        "body_data": body_data,  # Base64 encoded
                        "size_estimate": msg.get("sizeEstimate"),
                        "internal_date": msg.get("internalDate")
                    })

                # Format successful response
                return json.dumps({
                    "success": True,
                    "thread_id": thread_data.get("id", self.thread_id),
                    "message_count": len(processed_messages),
                    "messages": processed_messages,
                    "history_id": thread_data.get("historyId"),
                    "raw_thread_data": thread_data,  # Full thread data for advanced processing
                    "fetched_via": "composio"
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "message": f"Failed to fetch thread {self.thread_id}",
                    "thread_id": self.thread_id,
                    "message_count": 0,
                    "messages": []
                }, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "error": f"API request failed: {str(e)}",


                "type": "RequestException"
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error fetching thread: {str(e)}",
                "type": type(e).__name__,
                "thread_id": self.thread_id,
                "message_count": 0,
                "messages": []
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailFetchMessageByThreadId...")
    print("=" * 60)

    # Test 1: Fetch thread with valid ID
    print("\n1. Fetch thread by ID:")
    tool = GmailFetchMessageByThreadId(thread_id="18c1234567890abcd")
    result = tool.run()
    print(result)

    # Test 2: Missing thread_id (should error via pydantic validation)
    print("\n2. Test with missing thread_id (should error):")
    try:
        tool = GmailFetchMessageByThreadId(thread_id="")
        result = tool.run()
        print(result)
    except Exception as e:
        print(f"Validation error: {e}")

    # Test 3: Fetch another thread
    print("\n3. Fetch another thread:")
    tool = GmailFetchMessageByThreadId(thread_id="18c9876543210zyxw")
    result = tool.run()
    print(result)

    # Test 4: Fetch thread with multiple messages
    print("\n4. Fetch thread with conversation:")
    tool = GmailFetchMessageByThreadId(thread_id="18cabcdef12345678")
    result = tool.run()
    print(result)

    print("\n" + "=" * 60)
    print("Test completed!")
    print("\nUsage Examples:")
    print("- 'Show me the full conversation with John' - Fetches entire thread")
    print("- 'Read all messages in this thread' - Gets complete conversation history")
    print("- 'What's the full email exchange about the project?' - Thread details")
    print("\nResponse Structure:")
    print("- success: bool - Whether fetch succeeded")
    print("- thread_id: str - The conversation ID")
    print("- message_count: int - Number of messages in thread")
    print("- messages: array - All messages with full details")
    print("  - message_id: Individual message ID")
    print("  - subject: Email subject")
    print("  - from: Sender email")
    print("  - to: Recipients")
    print("  - date: When message was sent")
    print("  - snippet: Preview text")
    print("  - body_data: Base64 encoded body (decode for full content)")
    print("  - labels: Message organization (INBOX, UNREAD, etc.)")
    print("\nProduction Requirements:")
    print("- Set COMPOSIO_API_KEY in .env")
    print("- Set GMAIL_CONNECTION_ID in .env")
    print("- Gmail account connected via Composio")
    print("\nNotes:")
    print("- Messages returned in chronological order (oldest to newest)")
    print("- Includes all replies, forwards in the conversation")
    print("- Body data is base64 encoded and needs decoding for display")
    print("- Use snippet for quick preview, body_data for full content")
    print("- thread_id can be obtained from GmailFetchEmails or GmailGetMessage")

#!/usr/bin/env python3
import json
import os
import requests

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailGetMessage(BaseTool):
    """
    Gets detailed information about a specific Gmail message by message ID.
    Returns full message details including subject, sender, recipients, body, labels, and metadata.
    """

    message_id: str = Field(
        ...,
        description="Gmail message ID (required). Example: '18c1234567890abcd'"
    )

    def run(self):
        """
        Fetches detailed message information via Composio REST API.
        Returns JSON string with complete message data.
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        entity_id = os.getenv("GMAIL_CONNECTION_ID")

        if not api_key or not entity_id:
            return json.dumps({
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env"
            }, indent=2)

        # Validate message_id
        if not self.message_id:
            return json.dumps({
                "error": "message_id is required"
            }, indent=2)

        try:
            # Prepare API request
            url = "https://backend.composio.dev/api/v2/actions/GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID/execute"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "connectedAccountId": entity_id,
                "input": {
                    "message_id": self.message_id
                }
            }

            # Execute via Composio REST API
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()

            # Check if successful
            if result.get("successfull") or result.get("data"):
                message_data = result.get("data", {})

                # Extract key fields for easier access
                headers_list = message_data.get("payload", {}).get("headers", [])

                # Helper function to get header value
                def get_header(name):
                    for header in headers_list:
                        if header.get("name", "").lower() == name.lower():
                            return header.get("value", "")
                    return ""

                # Extract message parts for body
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

                payload_data = message_data.get("payload", {})
                body_data = get_body_text(payload_data)

                # Format response with structured data
                return json.dumps({
                    "success": True,
                    "message_id": message_data.get("id"),
                    "thread_id": message_data.get("threadId"),
                    "labels": message_data.get("labelIds", []),
                    "snippet": message_data.get("snippet", ""),
                    "subject": get_header("Subject"),
                    "from": get_header("From"),
                    "to": get_header("To"),
                    "cc": get_header("Cc"),
                    "bcc": get_header("Bcc"),
                    "date": get_header("Date"),
                    "body_data": body_data,  # Base64 encoded
                    "size_estimate": message_data.get("sizeEstimate"),
                    "internal_date": message_data.get("internalDate"),
                    "raw_data": message_data,  # Full message data for advanced processing
                    "fetched_via": "composio"
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "message": f"Failed to fetch message {self.message_id}"
                }, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "error": f"API request failed: {str(e)}",
                "type": "RequestException",
                "message_id": self.message_id
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "error": f"Error fetching message: {str(e)}",
                "type": type(e).__name__,
                "message_id": self.message_id
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailGetMessage...")

    # Test 1: Fetch message with valid ID
    print("\n1. Fetch message by ID:")
    tool = GmailGetMessage(message_id="18c1234567890abcd")
    result = tool.run()
    print(result)

    # Test 2: Missing message_id (should error)
    print("\n2. Test with missing message_id (should error):")
    try:
        tool = GmailGetMessage(message_id="")
        result = tool.run()
        print(result)
    except Exception as e:
        print(f"Validation error: {e}")

    # Test 3: Fetch another message
    print("\n3. Fetch another message:")
    tool = GmailGetMessage(message_id="18c9876543210zyxw")
    result = tool.run()
    print(result)

    print("\nTest completed!")
    print("\nUsage notes:")
    print("- Requires valid Gmail message ID")
    print("- Returns full message details including body, headers, labels")
    print("- Body data is base64 encoded and needs decoding for display")
    print("- Use snippet for quick preview, body_data for full content")
    print("- Labels array shows message organization (INBOX, UNREAD, etc.)")

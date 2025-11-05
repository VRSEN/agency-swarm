#!/usr/bin/env python3
import json
import os
import requests

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailGetAttachment(BaseTool):
    """
    Downloads an email attachment from Gmail by attachment ID.
    Returns attachment data in base64 format along with metadata.

    Use Case:
    - "Download the attachment from John's email"
    - First use GmailGetMessage to find attachment_id, then use this tool
    """

    message_id: str = Field(
        ...,
        description="Gmail message ID containing the attachment (required). Example: '18c1234567890abcd'"
    )

    attachment_id: str = Field(
        ...,
        description="Attachment ID from message details (required). Example: 'ANGjdJ8w...'"
    )

    def run(self):
        """
        Downloads attachment via Composio Gmail API.
        Returns JSON string with attachment data (base64), size, and metadata.
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        connection_id = os.getenv("GMAIL_CONNECTION_ID")

        if not api_key or not connection_id:
            return json.dumps({
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env"
            }, indent=2)

        # Validate inputs
        if not self.message_id:
            return json.dumps({
                "error": "message_id is required"
            }, indent=2)

        if not self.attachment_id:
            return json.dumps({
                "error": "attachment_id is required"
            }, indent=2)

        try:            # Execute Gmail get attachment via Composio
            # Prepare API request
            url = "https://backend.composio.dev/api/v2/actions/GMAIL_GET_ATTACHMENT/execute"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "connectedAccountId": connection_id,
                "input": {
                    "message_id": self.message_id,
                    "attachment_id": self.attachment_id
                }
            }

            # Execute via Composio REST API
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()

            # Check if successful
            if result.get("successfull") or result.get("data"):
                attachment_data = result.get("data", {})

                # Extract attachment details
                return json.dumps({
                    "success": True,
                    "message_id": self.message_id,
                    "attachment_id": self.attachment_id,
                    "data": attachment_data.get("data", ""),  # Base64 encoded attachment
                    "size": attachment_data.get("size", 0),
                    "encoding": "base64",
                    "note": "Use base64.b64decode() to convert data to binary",
                    "fetched_via": "composio"
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "message": f"Failed to download attachment {self.attachment_id} from message {self.message_id}"
                }, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "error": f"API request failed: {str(e)}",


                "type": "RequestException"
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "error": f"Error downloading attachment: {str(e)}",
                "type": type(e).__name__,
                "message_id": self.message_id,
                "attachment_id": self.attachment_id
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailGetAttachment...")
    print("\n" + "="*60)
    print("IMPORTANT: This tool requires valid message_id and attachment_id")
    print("Use GmailGetMessage first to find attachment IDs in messages")
    print("="*60)

    # Test 1: Download attachment with valid IDs
    print("\n1. Download attachment by ID:")
    print("   Usage: First get message details to find attachment_id")
    tool = GmailGetAttachment(
        message_id="18c1234567890abcd",
        attachment_id="ANGjdJ8w_example_attachment_id"
    )
    result = tool.run()
    print(result)

    # Test 2: Missing message_id (should error)
    print("\n2. Test with missing message_id (should error):")
    try:
        tool = GmailGetAttachment(
            message_id="",
            attachment_id="ANGjdJ8w_example"
        )
        result = tool.run()
        print(result)
    except Exception as e:
        print(f"Validation error: {e}")

    # Test 3: Missing attachment_id (should error)
    print("\n3. Test with missing attachment_id (should error):")
    try:
        tool = GmailGetAttachment(
            message_id="18c1234567890abcd",
            attachment_id=""
        )
        result = tool.run()
        print(result)
    except Exception as e:
        print(f"Validation error: {e}")

    # Test 4: Download another attachment
    print("\n4. Download another attachment:")
    tool = GmailGetAttachment(
        message_id="18c9876543210zyxw",
        attachment_id="ANGjdJ8w_another_attachment"
    )
    result = tool.run()
    print(result)

    print("\n" + "="*60)
    print("Test completed!")
    print("\nUsage workflow:")
    print("1. Use GmailFetchEmails to find messages with attachments")
    print("2. Use GmailGetMessage to get message details and attachment_id")
    print("3. Use GmailGetAttachment to download the attachment data")
    print("\nAttachment data:")
    print("- Returned as base64 encoded string")
    print("- Use Python's base64.b64decode() to convert to binary")
    print("- Save to file or process as needed")
    print("\nExample:")
    print("  import base64")
    print("  binary_data = base64.b64decode(attachment_data['data'])")
    print("  with open('downloaded_file.pdf', 'wb') as f:")
    print("      f.write(binary_data)")
    print("="*60)

#!/usr/bin/env python3
"""
GmailGetProfile Tool - Gets Gmail user profile information using Composio SDK.

Based on validated pattern from FINAL_VALIDATION_SUMMARY.md
Uses Composio SDK client.tools.execute() with GMAIL_GET_PROFILE action.
"""
import json
import os

from composio import Composio
from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailGetProfile(BaseTool):
    """
    Gets Gmail user profile information including email address, message count, and thread count.

    Returns comprehensive profile data:
    - Email address (primary Gmail account address)
    - Total message count (all messages in mailbox)
    - Total thread count (all conversation threads)
    - History ID (for tracking mailbox changes)
    - Messages per thread ratio (average messages per conversation)

    Use cases:
    - "What's my Gmail address?"
    - "How many emails do I have?"
    - "Show my Gmail profile"
    - System status and quota checks
    - Mailbox statistics and health monitoring
    """

    user_id: str = Field(
        default="me",
        description="Gmail user ID to get profile for. Use 'me' for authenticated user (default)."
    )

    def run(self):
        """
        Executes GMAIL_GET_PROFILE via Composio SDK.

        Returns:
            JSON string with:
            - success: bool - Whether profile fetch was successful
            - email_address: str - Primary Gmail email address
            - messages_total: int - Total number of messages in mailbox
            - threads_total: int - Total number of conversation threads
            - history_id: str - Mailbox history identifier
            - messages_per_thread: float - Average messages per thread
            - error: str - Error message if failed
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        entity_id = os.getenv("GMAIL_ENTITY_ID")

        if not api_key or not entity_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env",
                "email_address": None,
                "messages_total": 0,
                "threads_total": 0,
                "history_id": None,
                "messages_per_thread": 0.0,
                "profile_summary": None,
                "user_id": self.user_id
            }, indent=2)

        try:
            # Initialize Composio client
            client = Composio(api_key=api_key)

            # Execute GMAIL_GET_PROFILE via Composio
            result = client.tools.execute(
                "GMAIL_GET_PROFILE",
                {
                    "user_id": self.user_id
                },
                user_id=entity_id
            )

            # Extract profile data from response
            profile_data = result.get("data", {})

            # Get core profile fields
            email_address = profile_data.get("emailAddress", "N/A")
            messages_total = profile_data.get("messagesTotal", 0)
            threads_total = profile_data.get("threadsTotal", 0)
            history_id = profile_data.get("historyId", "N/A")

            # Calculate messages per thread ratio
            messages_per_thread = 0.0
            if threads_total > 0:
                messages_per_thread = round(messages_total / threads_total, 2)

            # Format successful response
            return json.dumps({
                "success": True,
                "email_address": email_address,
                "messages_total": messages_total,
                "threads_total": threads_total,
                "history_id": history_id,
                "messages_per_thread": messages_per_thread,
                "profile_summary": f"{email_address} has {messages_total} messages in {threads_total} threads",
                "user_id": self.user_id
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error fetching Gmail profile: {str(e)}",
                "type": type(e).__name__,
                "email_address": None,
                "messages_total": 0,
                "threads_total": 0,
                "history_id": None,
                "messages_per_thread": 0.0,
                "profile_summary": None,
                "user_id": self.user_id
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailGetProfile...")
    print("=" * 60)

    # Test 1: Get default user profile (me)
    print("\n1. Get profile for authenticated user (default):")
    tool = GmailGetProfile()
    result = tool.run()
    print(result)

    # Test 2: Explicitly specify 'me' as user_id
    print("\n2. Get profile with explicit 'me' user_id:")
    tool = GmailGetProfile(user_id="me")
    result = tool.run()
    print(result)

    # Test 3: Parse and display profile data
    print("\n3. Parse profile data and display formatted:")
    tool = GmailGetProfile()
    result_str = tool.run()
    result_data = json.loads(result_str)

    if result_data.get("success"):
        print(f"Email: {result_data['email_address']}")
        print(f"Total Messages: {result_data['messages_total']:,}")
        print(f"Total Threads: {result_data['threads_total']:,}")
        print(f"Messages per Thread: {result_data['messages_per_thread']}")
        print(f"History ID: {result_data['history_id']}")
    else:
        print(f"Error: {result_data.get('error')}")

    # Test 4: Test without credentials (should fail gracefully)
    print("\n4. Test without credentials (simulated):")
    # Save current env vars
    original_api_key = os.getenv("COMPOSIO_API_KEY")
    original_entity_id = os.getenv("GMAIL_ENTITY_ID")

    # Temporarily clear env vars
    if "COMPOSIO_API_KEY" in os.environ:
        del os.environ["COMPOSIO_API_KEY"]
    if "GMAIL_ENTITY_ID" in os.environ:
        del os.environ["GMAIL_ENTITY_ID"]

    tool = GmailGetProfile()
    result = tool.run()
    print(result)

    # Restore env vars
    if original_api_key:
        os.environ["COMPOSIO_API_KEY"] = original_api_key
    if original_entity_id:
        os.environ["GMAIL_ENTITY_ID"] = original_entity_id

    # Test 5: Check mailbox health (message to thread ratio)
    print("\n5. Mailbox health analysis:")
    tool = GmailGetProfile()
    result_str = tool.run()
    result_data = json.loads(result_str)

    if result_data.get("success"):
        ratio = result_data.get("messages_per_thread", 0)
        print(f"\nMailbox Statistics:")
        print(f"Messages per Thread Ratio: {ratio}")
        if ratio > 0:
            if ratio < 2:
                health = "Healthy - Most emails are standalone"
            elif ratio < 5:
                health = "Normal - Moderate conversation activity"
            elif ratio < 10:
                health = "Active - High conversation engagement"
            else:
                health = "Very Active - Extensive email threads"
            print(f"Mailbox Health: {health}")

    print("\n" + "=" * 60)
    print("Test completed!")
    print("\nGmailGetProfile Use Cases:")
    print("- Verify authenticated Gmail account")
    print("- Check total message and thread counts")
    print("- Monitor mailbox statistics")
    print("- System health checks")
    print("- Quota and usage monitoring")
    print("\nProduction Requirements:")
    print("- Set COMPOSIO_API_KEY in .env")
    print("- Set GMAIL_ENTITY_ID in .env")
    print("- Gmail account connected via Composio")

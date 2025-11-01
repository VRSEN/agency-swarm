#!/usr/bin/env python3
"""
Test Gmail integration via Composio API
Sends a real test email from info@mtlcraftcocktails.com
"""

import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

def test_gmail_send():
    """Send a test email via Composio Gmail integration"""

    # Get credentials from environment
    composio_api_key = os.getenv("COMPOSIO_API_KEY")
    connection_id = os.getenv("GMAIL_CONNECTION_ID")
    entity_id = os.getenv("GMAIL_ENTITY_ID")
    gmail_account = os.getenv("GMAIL_ACCOUNT")

    print("=" * 80)
    print("GMAIL COMPOSIO INTEGRATION TEST")
    print("=" * 80)
    print(f"\nGmail Account: {gmail_account}")
    print(f"Connection ID: {connection_id}")
    print(f"Entity ID: {entity_id}")
    print("\n" + "-" * 80)

    if not all([composio_api_key, connection_id]):
        print("❌ ERROR: Missing required credentials in .env")
        return False

    # Composio API endpoint for Gmail send
    url = f"https://backend.composio.dev/api/v2/actions/gmail_send_email/execute"

    headers = {
        "X-API-Key": composio_api_key,
        "Content-Type": "application/json"
    }

    # Test email content
    test_email = {
        "connectedAccountId": connection_id,
        "input": {
            "recipient_email": gmail_account,  # Send to self for testing
            "subject": "MTL Craft Cocktails - Gmail Integration Test",
            "body": """Hello from MTL Craft Cocktails!

This is a test email to verify our Voice-to-Email system is working correctly.

System Components Tested:
✅ Composio Gmail OAuth Integration
✅ API Authentication
✅ Email Send via info@mtlcraftcocktails.com

If you're reading this, the integration is successful!

---
Powered by Voice Email Telegram Agency
Test Date: October 31, 2025
""",
            "is_html": False
        }
    }

    print("Sending test email...")
    print(f"To: {gmail_account}")
    print(f"Subject: {test_email['input']['subject']}")
    print("\n" + "-" * 80)

    try:
        response = requests.post(url, headers=headers, json=test_email, timeout=30)

        print(f"\nAPI Response Status: {response.status_code}")

        if response.status_code == 200 or response.status_code == 201:
            result = response.json()
            print("\n✅ SUCCESS! Email sent successfully!")
            print("\nResponse:")
            print(json.dumps(result, indent=2))
            print("\n" + "=" * 80)
            print("CHECK YOUR INBOX: info@mtlcraftcocktails.com")
            print("=" * 80)
            return True
        else:
            print(f"\n❌ ERROR: Failed to send email")
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"\n❌ EXCEPTION: {str(e)}")
        return False


def test_gmail_list():
    """List recent emails to verify read access"""

    composio_api_key = os.getenv("COMPOSIO_API_KEY")
    connection_id = os.getenv("GMAIL_CONNECTION_ID")

    url = f"https://backend.composio.dev/api/v2/actions/gmail_list_messages/execute"

    headers = {
        "X-API-Key": composio_api_key,
        "Content-Type": "application/json"
    }

    payload = {
        "connectedAccountId": connection_id,
        "input": {
            "maxResults": 5,
            "q": "in:inbox"
        }
    }

    print("\n" + "=" * 80)
    print("TESTING GMAIL READ ACCESS")
    print("=" * 80)

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if response.status_code == 200:
            result = response.json()
            print("\n✅ Gmail Read Access: WORKING")
            messages = result.get("data", {}).get("messages", [])
            print(f"Found {len(messages)} recent messages")
            return True
        else:
            print(f"\n⚠️ Gmail Read Access: {response.status_code}")
            print(response.text)
            return False

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        return False


if __name__ == "__main__":
    print("\nStarting Gmail Composio Integration Tests...\n")

    # Test: Send email
    send_success = test_gmail_send()

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Gmail Send Email:  {'✅ PASS' if send_success else '❌ FAIL'}")
    print("=" * 80)

    if send_success:
        print("\n🎉 Gmail integration is fully operational!")
        print("📧 Check inbox: info@mtlcraftcocktails.com")
    else:
        print("\n⚠️ Gmail integration needs troubleshooting")

#!/usr/bin/env python3
"""
Test Gmail sending via Composio REST API v3
"""
import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("COMPOSIO_API_KEY")
connection_id = os.getenv("GMAIL_CONNECTION_ID")
entity_id = os.getenv("GMAIL_ENTITY_ID")
gmail_account = os.getenv("GMAIL_ACCOUNT")

print("=" * 80)
print("GMAIL COMPOSIO REST API TEST (V3)")
print("=" * 80)
print(f"\nConnection ID: {connection_id}")
print(f"Entity ID: {entity_id}")
print(f"Gmail Account: {gmail_account}")

# Try v3 endpoint structure
url = "https://backend.composio.dev/api/v3/actions/GMAIL_SEND_EMAIL/execute"

headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}

payload = {
    "connectedAccountId": connection_id,
    "input": {
        "recipient_email": gmail_account,
        "subject": "MTL Craft Cocktails - V3 API Test",
        "body": """Hello from MTL Craft Cocktails!

This is a test email via Composio API v3.

System Components:
✅ Composio Gmail OAuth
✅ REST API v3
✅ Connected account execution

If you're reading this, the v3 integration works!

---
Powered by Voice Email Telegram Agency
Test Date: October 31, 2025
""",
        "is_html": False
    }
}

print("\n" + "-" * 80)
print("Sending via v3 API...")
print("-" * 80)
print(f"URL: {url}")

try:
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    
    print(f"\nStatus Code: {response.status_code}")
    
    if response.status_code in [200, 201]:
        result = response.json()
        print("\n✅ SUCCESS!")
        print(json.dumps(result, indent=2))
        print("\n" + "=" * 80)
        print("📧 CHECK INBOX: info@mtlcraftcocktails.com")
        print("=" * 80)
    else:
        print(f"\n❌ ERROR")
        print(f"Response: {response.text}")
        
except Exception as e:
    print(f"\n❌ Exception: {str(e)}")
    import traceback
    traceback.print_exc()

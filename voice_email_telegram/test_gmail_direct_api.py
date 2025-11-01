#!/usr/bin/env python3
"""
Test Gmail sending via direct Composio REST API (v1 endpoint)
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
print("GMAIL COMPOSIO REST API TEST (V1)")
print("=" * 80)
print(f"\nConnection ID: {connection_id}")
print(f"Entity ID: {entity_id}")
print(f"Gmail Account: {gmail_account}")

# Try v1 endpoint structure
url = f"https://backend.composio.dev/api/v1/connectedAccounts/{connection_id}/actions/GMAIL_SEND_EMAIL"

headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}

payload = {
    "recipient_email": gmail_account,
    "subject": "MTL Craft Cocktails - Integration Test",
    "body": """Hello from MTL Craft Cocktails!

This is a test email to verify our Gmail integration via Composio API v1.

System Components:
✅ Composio Gmail OAuth
✅ REST API v1  
✅ Direct connected account execution

If you're reading this, the integration works!

---
Powered by Voice Email Telegram Agency
Test Date: October 31, 2025
""",
    "is_html": False
}

print("\n" + "-" * 80)
print("Sending via v1 API...")
print("-" * 80)
print(f"URL: {url}")
print(f"Payload: {json.dumps(payload, indent=2)}")

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

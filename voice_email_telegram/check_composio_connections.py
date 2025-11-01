#!/usr/bin/env python3
"""
Check Composio connected accounts to find correct Gmail connection ID
"""
import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("COMPOSIO_API_KEY")
entity_id = os.getenv("GMAIL_ENTITY_ID")

print("=" * 80)
print("CHECKING COMPOSIO CONNECTIONS")
print("=" * 80)
print(f"\nEntity ID: {entity_id}")
print(f"API Key: {api_key[:10]}...")

# Get connected accounts for this entity
url = f"https://backend.composio.dev/api/v1/connectedAccounts"

headers = {
    "X-API-Key": api_key,
}

params = {
    "user_uuid": entity_id
}

print("\nFetching connected accounts...")
try:
    response = requests.get(url, headers=headers, params=params, timeout=30)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print("\nConnected Accounts:")
        print(json.dumps(data, indent=2))
        
        # Look for Gmail connection
        if "items" in data:
            for account in data["items"]:
                if account.get("appName") == "gmail":
                    print(f"\n✅ Found Gmail Connection!")
                    print(f"Connection ID: {account.get('id')}")
                    print(f"App: {account.get('appName')}")
                    print(f"Status: {account.get('status')}")
    else:
        print(f"Error: {response.text}")
        
except Exception as e:
    print(f"Exception: {str(e)}")

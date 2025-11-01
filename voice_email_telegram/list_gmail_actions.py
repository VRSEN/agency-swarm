#!/usr/bin/env python3
"""
List available Gmail actions in Composio
"""
import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("COMPOSIO_API_KEY")

print("=" * 80)
print("LISTING GMAIL ACTIONS")
print("=" * 80)

# Get actions for Gmail
url = "https://backend.composio.dev/api/v2/actions"

headers = {
    "X-API-Key": api_key,
}

params = {
    "appNames": "gmail",
    "showAll": "true"
}

print("\nFetching Gmail actions...")
try:
    response = requests.get(url, headers=headers, params=params, timeout=30)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        actions = data.get("items", [])
        
        print(f"\nFound {len(actions)} Gmail actions")
        print("\n" + "-" * 80)
        
        # Look for send/list actions
        send_actions = [a for a in actions if "send" in a.get("name", "").lower() or "create" in a.get("name", "").lower()]
        list_actions = [a for a in actions if "list" in a.get("name", "").lower() or "get" in a.get("name", "").lower()]
        
        print("\n📧 SEND/CREATE ACTIONS:")
        for action in send_actions[:10]:
            print(f"  • {action.get('name')} - {action.get('description', '')[:80]}")
            
        print("\n📋 LIST/GET ACTIONS:")
        for action in list_actions[:10]:
            print(f"  • {action.get('name')} - {action.get('description', '')[:80]}")
            
    else:
        print(f"Error: {response.text}")
        
except Exception as e:
    print(f"Exception: {str(e)}")

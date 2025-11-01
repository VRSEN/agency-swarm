#!/usr/bin/env python3
"""
Find Gmail send and list actions
"""
import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("COMPOSIO_API_KEY")

print("=" * 80)
print("SEARCHING FOR GMAIL ACTIONS")
print("=" * 80)

# Search for Gmail send action
search_terms = ["GMAIL_SEND", "GMAIL_CREATE", "GMAIL_LIST", "GMAIL_GET"]

for term in search_terms:
    url = f"https://backend.composio.dev/api/v2/actions"
    
    headers = {
        "X-API-Key": api_key,
    }
    
    params = {
        "appNames": "gmail",
        "actions": term,
        "showAll": "true"
    }
    
    print(f"\nSearching for: {term}")
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            actions = data.get("items", [])
            
            if actions:
                print(f"  ✅ Found {len(actions)} action(s):")
                for action in actions[:5]:
                    print(f"    • {action.get('name')}")
                    print(f"      {action.get('description', '')[:100]}")
            else:
                print(f"  ❌ No actions found")
                
    except Exception as e:
        print(f"  ⚠️ Error: {str(e)}")

print("\n" + "=" * 80)
print("TRYING DIRECT ACTION CHECK")
print("=" * 80)

# Try the exact action names
action_names = [
    "GMAIL_SEND_EMAIL",
    "GMAIL_SEND_MESSAGE", 
    "GMAIL_CREATE_DRAFT",
    "GMAIL_LIST_MESSAGES"
]

for action_name in action_names:
    url = f"https://backend.composio.dev/api/v2/actions/{action_name}"
    headers = {"X-API-Key": api_key}
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            print(f"✅ {action_name} - EXISTS")
        else:
            print(f"❌ {action_name} - NOT FOUND ({response.status_code})")
    except Exception as e:
        print(f"⚠️ {action_name} - ERROR: {str(e)}")

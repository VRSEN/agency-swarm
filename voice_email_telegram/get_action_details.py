#!/usr/bin/env python3
"""
Get details for GMAIL_SEND_EMAIL action
"""
import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("COMPOSIO_API_KEY")

print("=" * 80)
print("GMAIL_SEND_EMAIL ACTION DETAILS")
print("=" * 80)

url = "https://backend.composio.dev/api/v2/actions/GMAIL_SEND_EMAIL"
headers = {"X-API-Key": api_key}

try:
    response = requests.get(url, headers=headers, timeout=30)
    
    if response.status_code == 200:
        action = response.json()
        print(f"\nAction Name: {action.get('name')}")
        print(f"Display Name: {action.get('displayName')}")
        print(f"Description: {action.get('description')}")
        print(f"\nApp: {action.get('appName')}")
        print(f"Enabled: {action.get('enabled')}")
        
        print("\n" + "-" * 80)
        print("PARAMETERS:")
        params = action.get('parameters', {})
        if 'properties' in params:
            for param_name, param_info in params['properties'].items():
                required = " (REQUIRED)" if param_name in params.get('required', []) else ""
                print(f"  • {param_name}{required}")
                print(f"    Type: {param_info.get('type')}")
                print(f"    Description: {param_info.get('description', 'N/A')}")
        
        print("\n" + "-" * 80)
        print("RESPONSE SCHEMA:")
        response_schema = action.get('response', {})
        print(json.dumps(response_schema, indent=2))
        
        print("\n" + "=" * 80)
        print("EXECUTION URL:")
        print(f"POST https://backend.composio.dev/api/v2/actions/GMAIL_SEND_EMAIL/execute")
        
    else:
        print(f"Error {response.status_code}: {response.text}")
        
except Exception as e:
    print(f"Exception: {str(e)}")

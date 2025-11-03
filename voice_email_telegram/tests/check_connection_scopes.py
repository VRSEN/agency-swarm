#!/usr/bin/env python3
"""
Check the Google connection scopes to see if Google Sheets access is enabled.
"""
import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("COMPOSIO_API_KEY")
connection_id = os.getenv("GMAIL_CONNECTION_ID")

if not api_key or not connection_id:
    print("ERROR: Missing COMPOSIO_API_KEY or GMAIL_CONNECTION_ID")
    exit(1)

print("Checking connection scopes...")
print("=" * 80)
print(f"Connection ID: {connection_id}")
print("=" * 80)

# Get connection details
url = f"https://backend.composio.dev/api/v2/connectedAccounts/{connection_id}"
headers = {"X-API-Key": api_key}

try:
    response = requests.get(url, headers=headers, timeout=10)

    if response.status_code == 200:
        data = response.json()

        print("\nConnection Details:")
        print(f"  App Name: {data.get('appName', 'N/A')}")
        print(f"  Status: {data.get('status', 'N/A')}")
        print(f"  Created At: {data.get('createdAt', 'N/A')}")

        # Check scopes
        connection_params = data.get('connectionParams', {})
        scopes = connection_params.get('scope', '')

        print(f"\nCurrent Scopes:")
        if isinstance(scopes, str):
            scope_list = scopes.split(' ')
        elif isinstance(scopes, list):
            scope_list = scopes
        else:
            scope_list = []

        for scope in scope_list:
            print(f"  - {scope}")

        # Check if Google Sheets scope is present
        sheets_scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/spreadsheets.readonly',
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/drive.readonly'
        ]

        has_sheets_access = any(scope in scope_list for scope in sheets_scopes)

        print("\n" + "=" * 80)
        if has_sheets_access:
            print("✓ Connection HAS Google Sheets access")
        else:
            print("✗ Connection DOES NOT have Google Sheets access")
            print("\nRequired scopes for Google Sheets:")
            for scope in sheets_scopes:
                print(f"  - {scope}")
            print("\nTo fix:")
            print("1. Go to Composio dashboard")
            print("2. Re-authenticate the Gmail connection")
            print("3. Ensure Google Sheets scope is enabled")
            print("OR")
            print("4. Create a new connection with Google Sheets app")
        print("=" * 80)

    else:
        print(f"✗ Failed to get connection details: HTTP {response.status_code}")
        print(f"Response: {response.text[:500]}")

except Exception as e:
    print(f"✗ Error: {str(e)}")
    import traceback
    traceback.print_exc()

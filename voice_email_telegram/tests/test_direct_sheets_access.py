#!/usr/bin/env python3
"""
Test direct Google Sheets API access using Composio v2 execute endpoint.
This tests if we can access the user's Google Sheet with the current connection.
"""
import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("COMPOSIO_API_KEY")
connection_id = os.getenv("GMAIL_CONNECTION_ID")
sheet_id = "1s0Zd1Glk8-1XsUv5UNsSVkZW0m2LQ3FdKz9smML4N_0"

if not api_key or not connection_id:
    print("ERROR: Missing credentials")
    exit(1)

print("Testing direct Google Sheets access...")
print("=" * 80)
print(f"Sheet ID: {sheet_id}")
print(f"Connection ID: {connection_id[:20]}...")
print(f"Action: GOOGLESHEETS_BATCH_GET")
print("=" * 80)

# Try to fetch data from Google Sheets
url = "https://backend.composio.dev/api/v2/actions/GOOGLESHEETS_BATCH_GET/execute"
headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}
payload = {
    "connectedAccountId": connection_id,
    "input": {
        "spreadsheet_id": sheet_id,
        "ranges": ["Sheet1!A1:D10"]  # Small sample
    }
}

print("\nAttempting to fetch data...")

try:
    response = requests.post(url, headers=headers, json=payload, timeout=30)

    print(f"\nHTTP Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print("\n✓ SUCCESS! Google Sheets access is working")
        print(f"\nResponse structure:")
        print(json.dumps(data, indent=2)[:500] + "...")

    elif response.status_code == 401:
        print("\n✗ 401 Unauthorized - Connection doesn't have Google Sheets scope")
        print("\nPossible solutions:")
        print("1. The Gmail connection doesn't include Google Sheets scope")
        print("2. Need to create a separate Google Sheets connection")
        print("3. Re-authenticate with additional scopes")

        print("\n\nLet's check if we need to list all connected accounts...")

        # List entities
        list_url = "https://backend.composio.dev/api/v1/connectedAccounts"
        list_response = requests.get(list_url, headers={"x-api-key": api_key}, timeout=10)

        if list_response.status_code == 200:
            entities = list_response.json().get('items', [])
            print(f"\nFound {len(entities)} connected account(s):")

            for entity in entities:
                print(f"\n  ID: {entity.get('id')}")
                print(f"  App: {entity.get('appName')}")
                print(f"  Status: {entity.get('status')}")

            # Check if there's a Google Sheets specific connection
            sheets_connections = [e for e in entities if e.get('appName') == 'googlesheets']
            if sheets_connections:
                print(f"\n✓ Found {len(sheets_connections)} Google Sheets connection(s)!")
                print("Update .env with one of these:")
                for conn in sheets_connections:
                    print(f"  GOOGLESHEETS_CONNECTION_ID={conn.get('id')}")
            else:
                print("\n✗ No Google Sheets connections found")
                print("You need to create a Google Sheets connection in Composio dashboard")

    elif response.status_code == 404:
        print("\n✗ 404 Not Found - Action may not exist or connection invalid")
        print(f"Response: {response.text[:300]}")

    else:
        print(f"\n✗ Unexpected error: {response.status_code}")
        print(f"Response: {response.text[:500]}")

except Exception as e:
    print(f"\n✗ Error: {str(e)}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)

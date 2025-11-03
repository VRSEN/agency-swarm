#!/usr/bin/env python3
"""
Check Composio v3 API connections and available apps.
"""
import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("COMPOSIO_API_KEY")

if not api_key:
    print("ERROR: COMPOSIO_API_KEY not set")
    exit(1)

print("Checking Composio v3 API...")
print("=" * 80)

# List all connections
print("\n1. Listing all connections:")
url = "https://backend.composio.dev/api/v3/connectedAccounts"
headers = {"X-API-Key": api_key}

try:
    response = requests.get(url, headers=headers, timeout=10)

    if response.status_code == 200:
        data = response.json()
        connections = data.get('items', [])

        print(f"\nFound {len(connections)} connection(s):")

        for conn in connections:
            print(f"\n  Connection ID: {conn.get('id')}")
            print(f"  App Unique Name: {conn.get('appUniqueId')}")
            print(f"  Status: {conn.get('status')}")
            print(f"  Integration ID: {conn.get('integrationId')}")

    else:
        print(f"✗ Failed: HTTP {response.status_code}")
        print(f"Response: {response.text[:500]}")

except Exception as e:
    print(f"✗ Error: {str(e)}")

# Check available apps
print("\n" + "=" * 80)
print("\n2. Checking available apps (Google Sheets, Gmail):")

for app_name in ["googlesheets", "gmail"]:
    url = f"https://backend.composio.dev/api/v3/apps/{app_name}"

    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            print(f"\n  ✓ {app_name.upper()} app available")
            print(f"    Name: {data.get('name')}")
            print(f"    Description: {data.get('description', 'N/A')[:80]}...")
        else:
            print(f"\n  ✗ {app_name.upper()}: HTTP {response.status_code}")

    except Exception as e:
        print(f"\n  ✗ {app_name.upper()}: {str(e)}")

# List available actions for Google Sheets
print("\n" + "=" * 80)
print("\n3. Checking Google Sheets actions:")

url = "https://backend.composio.dev/api/v3/actions"
params = {"appNames": "googlesheets"}

try:
    response = requests.get(url, headers=headers, params=params, timeout=10)

    if response.status_code == 200:
        data = response.json()
        actions = data.get('items', [])

        print(f"\nFound {len(actions)} Google Sheets action(s):")
        for action in actions[:10]:  # Show first 10
            print(f"  - {action.get('name')}: {action.get('description', 'N/A')[:60]}...")

    else:
        print(f"✗ Failed: HTTP {response.status_code}")

except Exception as e:
    print(f"✗ Error: {str(e)}")

print("\n" + "=" * 80)

#!/usr/bin/env python3
"""
Quick verification script to check if Composio GOOGLESHEETS_BATCH_GET action is available.
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

print("Checking Composio GOOGLESHEETS_BATCH_GET action availability...")
print("=" * 60)

# Check if action exists
url = "https://backend.composio.dev/api/v2/actions/GOOGLESHEETS_BATCH_GET"
headers = {"X-API-Key": api_key}

try:
    response = requests.get(url, headers=headers, timeout=10)

    if response.status_code == 200:
        data = response.json()
        print("✓ GOOGLESHEETS_BATCH_GET action is available!")
        print(f"\nAction Name: {data.get('name', 'N/A')}")
        print(f"Description: {data.get('description', 'N/A')[:100]}...")
        print(f"App Name: {data.get('appName', 'N/A')}")
    else:
        print(f"✗ Action check failed: HTTP {response.status_code}")
        print(f"Response: {response.text[:200]}")

except Exception as e:
    print(f"✗ Error checking action: {str(e)}")

print("=" * 60)

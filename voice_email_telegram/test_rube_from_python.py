#!/usr/bin/env python3
"""
Test calling Rube MCP from Python (outside Claude Code)
This determines how Agency Swarm tools can access Rube MCP
"""

import json
import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 80)
print("TESTING RUBE MCP ACCESS FROM PYTHON")
print("=" * 80)

# Option 1: Check if Composio SDK has MCP support
print("\n1. Testing Composio SDK for MCP config support...")
try:
    from composio import Composio

    api_key = os.getenv("COMPOSIO_API_KEY")
    client = Composio(api_key=api_key)

    # Check if there's an MCP config parameter
    print(f"   Composio client methods: {[m for m in dir(client) if not m.startswith('_')]}")

    # Try to reference MCP config
    # From user's dashboard: MCP config ID is 3dd7e198-5e93-43b4-ab43-4b3e57a24ba8

except Exception as e:
    print(f"   ❌ Error: {str(e)}")

# Option 2: Check Composio CLI for MCP
print("\n2. Checking if composio CLI has MCP commands...")
import subprocess
try:
    result = subprocess.run(['composio', '--help'], capture_output=True, text=True)
    if 'mcp' in result.stdout.lower():
        print("   ✅ MCP support found in CLI")
        print(result.stdout)
    else:
        print("   ⚠️ No MCP commands in CLI help")
except Exception as e:
    print(f"   ❌ Error: {str(e)}")

# Option 3: Check environment for Rube MCP server
print("\n3. Checking for Rube MCP server configuration...")
mcp_vars = {k: v for k, v in os.environ.items() if 'MCP' in k.upper() or 'RUBE' in k.upper()}
if mcp_vars:
    print("   ✅ MCP-related env vars found:")
    for k, v in mcp_vars.items():
        print(f"      {k}={v[:50]}..." if len(v) > 50 else f"      {k}={v}")
else:
    print("   ⚠️ No MCP env vars found")

# Option 4: Direct HTTP to Composio API with MCP config reference
print("\n4. Testing Composio API with MCP config...")
import requests

api_key = os.getenv("COMPOSIO_API_KEY")
mcp_config_id = "3dd7e198-5e93-43b4-ab43-4b3e57a24ba8"

headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}

# Try v1 API (tools execute endpoint)
try:
    url = "https://backend.composio.dev/api/v1/actions/GMAIL_FETCH_EMAILS/execute"
    payload = {
        "input": {
            "query": "is:unread",
            "max_results": 1,
            "user_id": "me"
        },
        "entityId": os.getenv("GMAIL_ENTITY_ID"),
        "connectedAccountId": os.getenv("GMAIL_CONNECTION_ID")
    }

    print(f"   Calling: {url}")
    response = requests.post(url, json=payload, headers=headers)
    print(f"   Status: {response.status_code}")

    if response.status_code == 200:
        print("   ✅ Direct API call works!")
        result = response.json()
        print(f"   Response: {json.dumps(result, indent=2)[:500]}...")
    else:
        print(f"   ❌ Error: {response.text[:200]}")

except Exception as e:
    print(f"   ❌ Error: {str(e)}")

# Option 5: Check if we can import Rube MCP directly
print("\n5. Checking for Rube MCP Python module...")
try:
    # This would only work if Rube MCP is installed as a Python package
    import mcp
    print(f"   ✅ MCP module found: {mcp}")
except ImportError:
    print("   ⚠️ MCP module not installed")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("""
The Telegram bot runs outside Claude Code, so we need a way to call Rube MCP.

OPTIONS:
A. Use Composio SDK with direct API calls (if Option 4 works)
B. Install and configure Rube MCP as Python module
C. Set up Rube MCP HTTP server and call it
D. Run bot inside Claude Code to access mcp__rube__ directly

Recommendation: Test which option works first.
""")

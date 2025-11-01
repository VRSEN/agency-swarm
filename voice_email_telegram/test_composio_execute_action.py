#!/usr/bin/env python3
"""
Test Composio execute_action method based on validated docs
Testing both ComposioToolSet.execute_action and Composio.tools.execute
"""

import json
import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 80)
print("TESTING COMPOSIO EXECUTE_ACTION PATTERNS")
print("=" * 80)

api_key = os.getenv("COMPOSIO_API_KEY")
entity_id = os.getenv("GMAIL_ENTITY_ID")

# Pattern 1: Using ComposioToolSet (from docs)
print("\n1. Testing ComposioToolSet.execute_action()...")
try:
    from composio import ComposioToolSet, Action

    toolset = ComposioToolSet(api_key=api_key)

    # Test GMAIL_FETCH_EMAILS
    result = toolset.execute_action(
        action=Action.GMAIL_FETCH_EMAILS,  # Or just the string "GMAIL_FETCH_EMAILS"
        params={
            "query": "is:unread",
            "max_results": 2,
            "user_id": "me"
        },
        entity_id=entity_id
    )

    print(f"   ✅ ComposioToolSet.execute_action works!")
    print(f"   Result: {json.dumps(result, indent=2)[:300]}...")

except Exception as e:
    print(f"   ❌ Error: {str(e)}")

# Pattern 2: Using Composio client (what we currently use)
print("\n2. Testing Composio.tools.execute()...")
try:
    from composio import Composio

    client = Composio(api_key=api_key)

    result = client.tools.execute(
        "GMAIL_FETCH_EMAILS",
        {
            "query": "is:unread",
            "max_results": 2,
            "user_id": "me"
        },
        user_id=entity_id,
        dangerously_skip_version_check=True
    )

    print(f"   ✅ Composio.tools.execute works!")
    print(f"   Result: {json.dumps(result, indent=2)[:300] if isinstance(result, dict) else str(result)[:300]}...")

except Exception as e:
    print(f"   ❌ Error: {str(e)}")

# Pattern 3: Check if composio_core has different API
print("\n3. Testing composio_core (if available)...")
try:
    from composio_core import ComposioToolSet as CoreToolSet

    toolset = CoreToolSet(api_key=api_key)

    result = toolset.execute_action(
        action="GMAIL_FETCH_EMAILS",
        params={
            "query": "is:unread",
            "max_results": 2
        },
        entity_id=entity_id
    )

    print(f"   ✅ composio_core works!")
    print(f"   Result: {json.dumps(result, indent=2)[:300]}...")

except ImportError:
    print(f"   ⚠️ composio_core not installed")
except Exception as e:
    print(f"   ❌ Error: {str(e)}")

# Pattern 4: Try with connected_account_id instead of entity_id
print("\n4. Testing with connected_account_id...")
try:
    from composio import Composio

    client = Composio(api_key=api_key)
    connection_id = os.getenv("GMAIL_CONNECTION_ID")

    result = client.tools.execute(
        "GMAIL_FETCH_EMAILS",
        {
            "query": "is:unread",
            "max_results": 2,
            "user_id": "me"
        },
        connected_account_id=connection_id,
        dangerously_skip_version_check=True
    )

    print(f"   ✅ connected_account_id works!")
    print(f"   Result: {json.dumps(result, indent=2)[:300] if isinstance(result, dict) else str(result)[:300]}...")

except Exception as e:
    print(f"   ❌ Error: {str(e)}")

# Check what's actually installed
print("\n5. Checking installed Composio packages...")
import subprocess
try:
    result = subprocess.run(['pip', 'list', '|', 'grep', 'composio'],
                          capture_output=True, text=True, shell=True)
    print(f"   {result.stdout}")
except Exception as e:
    print(f"   ❌ Error: {str(e)}")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("""
This test validates which Composio pattern works for our setup.
The working pattern will be used for all 27 Gmail tools.
""")

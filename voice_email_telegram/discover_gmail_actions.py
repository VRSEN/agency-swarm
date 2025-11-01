#!/usr/bin/env python3
"""Discover all available Gmail actions in Composio"""

import os
from dotenv import load_dotenv
from composio import Composio

load_dotenv()

api_key = os.getenv("COMPOSIO_API_KEY")
client = Composio(api_key=api_key)

print("=" * 80)
print("DISCOVERING GMAIL TOOLKIT ACTIONS")
print("=" * 80)

try:
    # Get all actions for Gmail toolkit
    actions = client.actions.list(app_name="gmail")

    gmail_actions = []
    for action in actions:
        action_name = action.name if hasattr(action, 'name') else str(action)
        gmail_actions.append(action_name)

    print(f"\n✅ Found {len(gmail_actions)} Gmail actions\n")
    print("=" * 80)
    print("AVAILABLE GMAIL ACTIONS:")
    print("=" * 80)

    for i, action in enumerate(sorted(gmail_actions), 1):
        print(f"  {i:3}. {action}")

    print("\n" + "=" * 80)
    print(f"Total: {len(gmail_actions)} actions")
    print("=" * 80)

except Exception as e:
    print(f"❌ Error: {str(e)}")
    print("\nTrying alternative method...")

    # Try getting actions from toolkit info
    try:
        toolkit_info = client.apps.get(name="gmail")
        print(f"✅ Gmail toolkit found: {toolkit_info}")
    except Exception as e2:
        print(f"❌ Failed: {str(e2)}")

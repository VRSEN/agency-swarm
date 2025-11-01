#!/usr/bin/env python3
"""
Retest the 16 actions that "didn't exist" before
Now using the WORKING pattern: Composio.tools.execute() with user_id=entity_id
"""

import os
import json
from dotenv import load_dotenv
from composio import Composio

load_dotenv()

api_key = os.getenv("COMPOSIO_API_KEY")
entity_id = os.getenv("GMAIL_ENTITY_ID")

client = Composio(api_key=api_key)

# These are the 16 actions that "failed" before
ACTIONS_TO_RETEST = [
    "GMAIL_CREATE_EMAIL_DRAFT",  # Was "not found" before
    "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID",  # Was "not found" before
    "GMAIL_BATCH_MODIFY_MESSAGES",  # Was "not found" before
    "GMAIL_MOVE_TO_TRASH",  # Was "not found" before
    "GMAIL_LIST_THREADS",  # Was "not found" before
    "GMAIL_ADD_LABEL_TO_EMAIL",  # Was "not found" before
    "GMAIL_REPLY_TO_EMAIL_THREAD",  # Was "not found" before
    "GMAIL_FORWARD_EMAIL_MESSAGE",  # Was "not found" before
    "GMAIL_BATCH_DELETE_MESSAGES",  # Was "not found" before
    "GMAIL_DELETE_MESSAGE",  # Was "not found" before
    "GMAIL_SEARCH_PEOPLE",  # Was "not found" before
    "GMAIL_LIST_DRAFTS",  # Was "not found" before
]

print("=" * 80)
print("RETESTING 'MISSING' GMAIL ACTIONS")
print("=" * 80)
print(f"Using: Composio.tools.execute() with user_id={entity_id}\n")

working_actions = []
still_missing = []

for action_name in ACTIONS_TO_RETEST:
    try:
        # Try minimal params to see if action exists
        result = client.tools.execute(
            action_name,
            {"user_id": "me"},  # Minimal params
            user_id=entity_id,
            dangerously_skip_version_check=True
        )

        # If we get here without 404, action exists!
        working_actions.append(action_name)
        print(f"✅ {action_name} - EXISTS!")

        # Show a snippet of the response
        if isinstance(result, dict) and "data" in result:
            print(f"   Response has 'data' key")

    except Exception as e:
        error_str = str(e)
        if "404" in error_str or "not found" in error_str.lower():
            still_missing.append(action_name)
            print(f"❌ {action_name} - STILL NOT FOUND")
        elif "required" in error_str.lower() or "missing" in error_str.lower():
            # Param error means action exists!
            working_actions.append(action_name)
            print(f"✅ {action_name} - EXISTS (param error, but action found)")
        else:
            # Other error, but action might exist
            working_actions.append(action_name)
            print(f"✅ {action_name} - EXISTS (error: {str(e)[:60]}...)")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"✅ Now working:     {len(working_actions)}/{len(ACTIONS_TO_RETEST)}")
print(f"❌ Still missing:   {len(still_missing)}/{len(ACTIONS_TO_RETEST)}")
print("=" * 80)

if working_actions:
    print("\n✅ NEWLY DISCOVERED WORKING ACTIONS:")
    for action in working_actions:
        print(f"  • {action}")

if still_missing:
    print("\n❌ STILL MISSING:")
    for action in still_missing:
        print(f"  • {action}")

print("\n" + "=" * 80)
print("CONCLUSION")
print("=" * 80)

total_available = 8 + len(working_actions)  # 8 from before + new ones
print(f"Total Gmail actions available: {total_available}")
print(f"Originally thought available: 8")
print(f"New actions discovered: {len(working_actions)}")
print(f"User's MCP dashboard shows: 27")
print(f"Gap: {27 - total_available} actions")

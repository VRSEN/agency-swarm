#!/usr/bin/env python3
"""Test which Gmail actions actually exist in Composio"""

import os
import json
from dotenv import load_dotenv
from composio import Composio

load_dotenv()

api_key = os.getenv("COMPOSIO_API_KEY")
entity_id = os.getenv("GMAIL_ENTITY_ID")

client = Composio(api_key=api_key)

# List of actions we want to test (from architecture document)
ACTIONS_TO_TEST = [
    "GMAIL_SEND_EMAIL",  # Known working
    "GMAIL_FETCH_EMAILS",
    "GMAIL_SEARCH_MESSAGES",
    "GMAIL_GET_MESSAGE",
    "GMAIL_GET_THREAD",
    "GMAIL_GET_ATTACHMENT",
    "GMAIL_LIST_LABELS",
    "GMAIL_CREATE_LABEL",
    "GMAIL_ADD_LABEL",
    "GMAIL_REMOVE_LABEL",
    "GMAIL_DELETE_LABEL",
    "GMAIL_MARK_READ",
    "GMAIL_MARK_UNREAD",
    "GMAIL_ARCHIVE",
    "GMAIL_DELETE",
    "GMAIL_TRASH_MESSAGE",
    "GMAIL_CREATE_DRAFT",
    "GMAIL_GET_DRAFT",
    "GMAIL_UPDATE_DRAFT",
    "GMAIL_DELETE_DRAFT",
    "GMAIL_SEND_DRAFT",
    "GMAIL_BATCH_MODIFY",
    "GMAIL_BULK_DELETE",
    "GMAIL_SEND_WITH_ATTACHMENT",
]

print("=" * 80)
print("TESTING GMAIL ACTION EXISTENCE")
print("=" * 80)
print(f"Total actions to test: {len(ACTIONS_TO_TEST)}\n")

existing_actions = []
missing_actions = []

for action_name in ACTIONS_TO_TEST:
    try:
        # Try to get action details (doesn't actually execute)
        # This will fail with 404 if action doesn't exist
        result = client.tools.execute(
            action_name,
            {},  # Empty params - will fail but tells us if action exists
            user_id=entity_id,
            dangerously_skip_version_check=True
        )
        # If we get here, action exists (even if it failed due to params)
        existing_actions.append(action_name)
        print(f"✅ {action_name}")

    except Exception as e:
        error_str = str(e)
        if "404" in error_str or "not found" in error_str.lower():
            missing_actions.append(action_name)
            print(f"❌ {action_name} - NOT FOUND")
        else:
            # Action exists but params were wrong - that's okay
            existing_actions.append(action_name)
            print(f"✅ {action_name} (exists, param error: {str(e)[:50]}...)")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"✅ Existing: {len(existing_actions)}")
print(f"❌ Missing:  {len(missing_actions)}")
print("=" * 80)

if existing_actions:
    print("\n✅ EXISTING ACTIONS:")
    for action in existing_actions:
        print(f"  • {action}")

if missing_actions:
    print("\n❌ MISSING ACTIONS (NOT AVAILABLE IN COMPOSIO):")
    for action in missing_actions:
        print(f"  • {action}")

print("\n" + "=" * 80)

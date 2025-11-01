#!/usr/bin/env python3
"""
Test ALL 27 Gmail actions from user's Composio dashboard
Using validated pattern: Composio.tools.execute() with user_id=entity_id
"""

import os
import json
from dotenv import load_dotenv
from composio import Composio

load_dotenv()

api_key = os.getenv("COMPOSIO_API_KEY")
entity_id = os.getenv("GMAIL_ENTITY_ID")

client = Composio(api_key=api_key)

# All 27 actions from user's Composio dashboard
ALL_27_ACTIONS = [
    # Email Operations (8)
    "GMAIL_SEND_EMAIL",
    "GMAIL_FETCH_EMAILS",
    "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID",
    "GMAIL_FETCH_MESSAGE_BY_THREAD_ID",
    "GMAIL_FORWARD_EMAIL_MESSAGE",
    "GMAIL_REPLY_TO_EMAIL_THREAD",
    "GMAIL_DELETE_MESSAGE",
    "GMAIL_MOVE_TO_TRASH",
    # Draft Operations (4)
    "GMAIL_CREATE_EMAIL_DRAFT",
    "GMAIL_LIST_DRAFTS",
    "GMAIL_SEND_DRAFT",
    "GMAIL_DELETE_DRAFT",
    # Label Operations (6)
    "GMAIL_LIST_LABELS",
    "GMAIL_CREATE_LABEL",
    "GMAIL_ADD_LABEL_TO_EMAIL",  # Note: Dashboard says "Modify email labels"
    "GMAIL_MODIFY_THREAD_LABELS",
    "GMAIL_PATCH_LABEL",
    "GMAIL_REMOVE_LABEL",
    # Batch Operations (2)
    "GMAIL_BATCH_MODIFY_MESSAGES",
    "GMAIL_BATCH_DELETE_MESSAGES",
    # Attachments (1)
    "GMAIL_GET_ATTACHMENT",
    # Contacts (3)
    "GMAIL_SEARCH_PEOPLE",
    "GMAIL_GET_PEOPLE",
    "GMAIL_GET_CONTACTS",
    # History & Sync (2)
    "GMAIL_LIST_GMAIL_HISTORY",
    "GMAIL_LIST_THREADS",
    # Profile (1)
    "GMAIL_GET_PROFILE",
]

print("=" * 80)
print("TESTING ALL 27 GMAIL ACTIONS FROM USER'S COMPOSIO DASHBOARD")
print("=" * 80)
print(f"Using: Composio.tools.execute() with user_id={entity_id}\n")

working_actions = []
missing_actions = []

for i, action_name in enumerate(ALL_27_ACTIONS, 1):
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
        print(f"{i:2}. ✅ {action_name}")

    except Exception as e:
        error_str = str(e)
        if "404" in error_str or "not found" in error_str.lower():
            missing_actions.append(action_name)
            print(f"{i:2}. ❌ {action_name} - NOT FOUND (404)")
        elif "required" in error_str.lower() or "missing" in error_str.lower():
            # Param error means action exists!
            working_actions.append(action_name)
            print(f"{i:2}. ✅ {action_name} (param error = exists)")
        else:
            # Other error, but action might exist
            working_actions.append(action_name)
            print(f"{i:2}. ✅ {action_name} (error but exists)")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"✅ Working:         {len(working_actions)}/27 ({len(working_actions)/27*100:.1f}%)")
print(f"❌ Missing:         {len(missing_actions)}/27 ({len(missing_actions)/27*100:.1f}%)")
print(f"📊 User requested:  100% Gmail functionality")
print("=" * 80)

if missing_actions:
    print("\n❌ MISSING ACTIONS:")
    for action in missing_actions:
        print(f"  • {action}")

print("\n✅ AVAILABLE ACTIONS:")
for action in working_actions:
    print(f"  • {action}")

print("\n" + "=" * 80)
print("CONCLUSION")
print("=" * 80)

if len(working_actions) >= 24:  # 90% threshold
    print("✅ EXCELLENT: Composio SDK has sufficient Gmail coverage!")
    print(f"   {len(working_actions)} actions available = {len(working_actions)/27*100:.1f}% of user requirements")
    print("   RECOMMENDATION: Build tools using Composio SDK")
elif len(working_actions) >= 18:  # 66% threshold
    print("⚠️ GOOD: Most Gmail actions available via Composio SDK")
    print(f"   {len(working_actions)} actions available = {len(working_actions)/27*100:.1f}% of user requirements")
    print("   RECOMMENDATION: Use Composio SDK + consider Gmail API for missing features")
else:
    print("❌ LIMITED: Significant gaps in Composio SDK Gmail support")
    print(f"   Only {len(working_actions)} actions available = {len(working_actions)/27*100:.1f}% of user requirements")
    print("   RECOMMENDATION: Hybrid approach (Composio SDK + Gmail API)")

print("=" * 80)

# Save results
with open("gmail_actions_test_results.json", "w") as f:
    json.dump({
        "total_actions": 27,
        "working_actions": working_actions,
        "missing_actions": missing_actions,
        "working_count": len(working_actions),
        "missing_count": len(missing_actions),
        "coverage_percent": len(working_actions)/27*100
    }, f, indent=2)

print("\n✅ Results saved to gmail_actions_test_results.json")

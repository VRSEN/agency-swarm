"""
Mem0 Data Exploration Script
Investigates what user_ids exist and what data is actually stored in Mem0.
"""

import os

from dotenv import load_dotenv
from mem0 import MemoryClient

load_dotenv()

def main():
    api_key = os.getenv("MEM0_API_KEY")
    if not api_key:
        print("ERROR: MEM0_API_KEY not found in .env")
        return

    print("=" * 80)
    print("MEM0 DATA EXPLORATION")
    print("=" * 80)

    client = MemoryClient(api_key=api_key)

    # Common user_ids to check
    user_ids_to_check = [
        'default',
        'chrome-extension-user',
        'ashley',
        'mtlcraftcocktails',
        'info@mtlcraftcocktails.com',
        'user_12345',
        'test',
        'admin',
    ]

    print("\n1. CHECKING COMMON USER IDS")
    print("-" * 80)

    results_by_user = {}

    for user_id in user_ids_to_check:
        try:
            print(f"\nChecking user_id: '{user_id}'...")
            memories = client.get_all(user_id=user_id)
            count = len(memories) if memories else 0
            print(f"  → Found {count} memories")

            if count > 0:
                results_by_user[user_id] = memories
                # Show first few memories
                print("  → Sample memories:")
                for i, mem in enumerate(memories[:3]):
                    print(f"     [{i+1}] {mem.get('memory', 'N/A')[:100]}...")
        except Exception as e:
            print(f"  → Error: {str(e)}")

    print("\n\n2. SUMMARY OF FOUND DATA")
    print("-" * 80)

    if not results_by_user:
        print("No memories found for any of the common user_ids.")
        print("\nThis suggests:")
        print("  - Data might be stored under a different user_id")
        print("  - The Mem0 dashboard might be showing data from a different account")
        print("  - The API key might be for a different workspace")
    else:
        print(f"Found memories in {len(results_by_user)} user_id(s):")
        for user_id, memories in results_by_user.items():
            print(f"\n  User ID: '{user_id}' - {len(memories)} memories")

    # Search for specific content across all found user_ids
    print("\n\n3. SEARCHING FOR SPECIFIC CONTENT")
    print("-" * 80)

    search_terms = [
        "Marc-Andre",
        "marc",
        "email",
        "contact",
        "@mtlcraftcocktails.com",
        "staff",
    ]

    for user_id in results_by_user.keys():
        print(f"\nSearching in user_id: '{user_id}'")
        for term in search_terms:
            try:
                results = client.search(query=term, user_id=user_id, limit=10)
                if results and len(results) > 0:
                    print(f"  '{term}': Found {len(results)} results")
                    for r in results[:2]:
                        print(f"    - {r.get('memory', 'N/A')[:100]}")
            except Exception as e:
                print(f"  '{term}': Error - {str(e)}")

    # Show all data for the most populated user_id
    if results_by_user:
        print("\n\n4. FULL DATA DUMP FOR MOST POPULATED USER")
        print("-" * 80)

        # Find user_id with most memories
        max_user_id = max(results_by_user.keys(), key=lambda k: len(results_by_user[k]))
        memories = results_by_user[max_user_id]

        print(f"\nUser ID: '{max_user_id}'")
        print(f"Total memories: {len(memories)}")
        print("\nAll memories:")

        # Group by content type
        emails_found = []
        contacts_found = []
        other = []

        for mem in memories:
            mem_text = mem.get('memory', '').lower()
            if 'email' in mem_text or '@' in mem_text:
                emails_found.append(mem)
            elif 'contact' in mem_text or 'name' in mem_text:
                contacts_found.append(mem)
            else:
                other.append(mem)

        print(f"\n  Email-related: {len(emails_found)}")
        for i, mem in enumerate(emails_found[:5]):
            print(f"    [{i+1}] {mem.get('memory', 'N/A')}")

        print(f"\n  Contact-related: {len(contacts_found)}")
        for i, mem in enumerate(contacts_found[:5]):
            print(f"    [{i+1}] {mem.get('memory', 'N/A')}")

        print(f"\n  Other: {len(other)}")
        for i, mem in enumerate(other[:5]):
            print(f"    [{i+1}] {mem.get('memory', 'N/A')}")

    # Search for Marc-Andre specifically
    print("\n\n5. SPECIFIC SEARCH: MARC-ANDRE")
    print("-" * 80)

    for user_id in results_by_user.keys():
        try:
            results = client.search(query="Marc-Andre", user_id=user_id, limit=20)
            if results and len(results) > 0:
                print(f"\nFound {len(results)} results for 'Marc-Andre' in user_id '{user_id}':")
                for r in results:
                    print(f"  - {r.get('memory', 'N/A')}")
        except Exception as e:
            print(f"Error searching for Marc-Andre in '{user_id}': {str(e)}")

    # Final recommendations
    print("\n\n6. RECOMMENDATIONS")
    print("-" * 80)

    if not results_by_user:
        print("""
The exploration found NO memories in any common user_ids.

Possible reasons:
1. The 1,500 memories in the dashboard are under a different user_id
2. You might be using a different Mem0 account/workspace
3. The API key might not match the dashboard you're viewing

Next steps:
1. Check your Mem0 dashboard - what user_id are the memories under?
2. Try to find what user_id was used when adding those 1,500 memories
3. Contact Mem0 support to verify which workspace this API key belongs to
        """)
    else:
        total_found = sum(len(mems) for mems in results_by_user.values())
        print(f"""
Found {total_found} total memories across {len(results_by_user)} user_id(s).

If the dashboard shows 1,500 memories but we only found {total_found}:
1. The dashboard might be showing data from ALL user_ids combined
2. There might be additional user_ids we didn't check
3. Try using the Mem0 API to list all user_ids in the workspace

To find the missing data:
1. Check what user_id was used when uploading the 1,500 memories
2. Look at your import scripts to see what user_id they use
3. Contact Mem0 support to help identify all user_ids in your workspace
        """)

    print("\n" + "=" * 80)
    print("EXPLORATION COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Context Window Management Test
Tests that EmailSpecialist can handle 25+ consecutive operations without context overflow.
"""
from agency import agency
from datetime import datetime

def test_context_management():
    """Simulate heavy email operations to test context window handling"""

    print("=" * 80)
    print("CONTEXT WINDOW MANAGEMENT TEST")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Testing 25 consecutive email operations...")
    print("=" * 80)

    operations = [
        ("Show me my latest email", "fetch latest"),
        ("What are my unread emails?", "fetch unread"),
        ("List emails from the last 3 days", "fetch recent"),
        ("Show emails from john@example.com", "fetch from sender"),
        ("Find emails with attachments", "fetch with attachments"),
        ("Check my starred emails", "fetch starred"),
        ("What emails did I receive today?", "fetch today"),
        ("Show me important emails", "fetch important"),
        ("List all emails in my inbox", "fetch inbox"),
        ("What's the most recent email?", "fetch latest"),
        ("Show unread messages", "fetch unread"),
        ("Find emails about 'meeting'", "search meetings"),
        ("Check emails from sarah@company.com", "fetch from sender"),
        ("Show my last 5 emails", "fetch last 5"),
        ("What emails came in yesterday?", "fetch yesterday"),
        ("List emails with 'urgent' in subject", "search urgent"),
        ("Show emails I starred", "fetch starred"),
        ("Check my inbox", "fetch inbox"),
        ("What are my latest messages?", "fetch latest"),
        ("Show emails from team@startup.com", "fetch from team"),
        ("Find emails about 'project update'", "search project"),
        ("List unread emails from this week", "fetch unread recent"),
        ("Show me all my emails", "fetch all"),
        ("What's in my inbox?", "fetch inbox"),
        ("Check for new messages", "fetch new"),
    ]

    results = []
    context_errors = 0

    for i, (query, description) in enumerate(operations, 1):
        print(f"\n[{i:2d}/25] {description}")
        print(f"        Query: '{query}'")

        try:
            response = agency.get_completion(query)

            # Check for context errors
            if "context_length_exceeded" in response.lower():
                print(f"        ❌ FAILED: Context overflow")
                context_errors += 1
                results.append({
                    "operation": i,
                    "query": query,
                    "status": "CONTEXT_ERROR",
                    "error": "context_length_exceeded"
                })
            elif "error" in response.lower() and "context" in response.lower():
                print(f"        ⚠️  WARNING: Possible context issue")
                print(f"        Response: {response[:150]}...")
                results.append({
                    "operation": i,
                    "query": query,
                    "status": "WARNING",
                    "response": response[:200]
                })
            else:
                print(f"        ✅ SUCCESS")
                results.append({
                    "operation": i,
                    "query": query,
                    "status": "SUCCESS"
                })

        except Exception as e:
            error_str = str(e)
            if "context_length_exceeded" in error_str or "context window" in error_str.lower():
                print(f"        ❌ FAILED: Context overflow exception")
                context_errors += 1
                results.append({
                    "operation": i,
                    "query": query,
                    "status": "CONTEXT_ERROR",
                    "error": error_str
                })
            else:
                print(f"        ❌ FAILED: {error_str}")
                results.append({
                    "operation": i,
                    "query": query,
                    "status": "ERROR",
                    "error": error_str
                })

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    success = sum(1 for r in results if r["status"] == "SUCCESS")
    warnings = sum(1 for r in results if r["status"] == "WARNING")
    errors = sum(1 for r in results if r["status"] == "ERROR")

    print(f"Total Operations: {len(operations)}")
    print(f"✅ Successful: {success}")
    print(f"⚠️  Warnings: {warnings}")
    print(f"❌ Context Errors: {context_errors}")
    print(f"❌ Other Errors: {errors - context_errors}")
    print()

    if context_errors == 0:
        print("🎉 PASS: No context window overflow errors!")
        print("✅ Context management working correctly")
    else:
        print(f"💥 FAIL: {context_errors} context overflow errors detected")
        print("❌ Context management needs attention")

    print("=" * 80)
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    return {
        "total": len(operations),
        "success": success,
        "warnings": warnings,
        "context_errors": context_errors,
        "other_errors": errors - context_errors,
        "passed": context_errors == 0
    }


if __name__ == "__main__":
    result = test_context_management()
    exit(0 if result["passed"] else 1)

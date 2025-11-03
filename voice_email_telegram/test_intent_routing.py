#!/usr/bin/env python3
"""
CEO Intent Routing Test
Tests that CEO correctly distinguishes FETCH vs DRAFT operations.
"""
from agency import agency
from datetime import datetime

def analyze_response(response, expected_intent):
    """
    Analyze agency response to determine if routing was correct.

    Args:
        response: String response from agency
        expected_intent: "FETCH" or "DRAFT"

    Returns:
        tuple: (actual_intent, is_correct, reasoning)
    """
    response_lower = response.lower()

    # FETCH indicators
    fetch_indicators = [
        "gmailfetchemails",
        "fetching emails",
        "showing emails",
        "here are your emails",
        "found emails",
        "search results",
        "inbox",
        "messages found"
    ]

    # DRAFT indicators
    draft_indicators = [
        "draft",
        "compose",
        "create email",
        "send email",
        "workflow",
        "voice handler",
        "email specialist",
        "approval",
        "would you like me to draft"
    ]

    # Check indicators
    fetch_count = sum(1 for indicator in fetch_indicators if indicator in response_lower)
    draft_count = sum(1 for indicator in draft_indicators if indicator in response_lower)

    if fetch_count > draft_count:
        actual_intent = "FETCH"
        reasoning = f"Found {fetch_count} fetch indicators vs {draft_count} draft indicators"
    elif draft_count > fetch_count:
        actual_intent = "DRAFT"
        reasoning = f"Found {draft_count} draft indicators vs {fetch_count} fetch indicators"
    else:
        # Ambiguous - try secondary analysis
        if "emailspecialist" in response_lower and "gmail" in response_lower:
            actual_intent = "FETCH"
            reasoning = "EmailSpecialist with Gmail tools suggests fetch"
        elif "voice" in response_lower or "memory" in response_lower:
            actual_intent = "DRAFT"
            reasoning = "Voice/Memory agents suggest draft workflow"
        else:
            actual_intent = "UNCLEAR"
            reasoning = "Cannot determine intent from response"

    is_correct = (actual_intent == expected_intent)

    return actual_intent, is_correct, reasoning


def test_intent_routing():
    """Test CEO's ability to route FETCH vs DRAFT operations correctly"""

    print("=" * 80)
    print("CEO INTENT ROUTING TEST")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Testing fetch vs draft intent classification...")
    print("=" * 80)

    test_cases = [
        # Format: (query, expected_intent, category)

        # FETCH test cases
        ("What is the last email that came in?", "FETCH", "Latest email fetch"),
        ("Show my latest email", "FETCH", "Latest email display"),
        ("Check my inbox", "FETCH", "Inbox check"),
        ("What are my unread emails?", "FETCH", "Unread query"),
        ("Find emails from john@example.com", "FETCH", "Sender search"),
        ("Read the email from Sarah", "FETCH", "Read request"),
        ("Show me my recent messages", "FETCH", "Recent messages"),
        ("List all emails about meetings", "FETCH", "Topic search"),

        # DRAFT test cases
        ("Draft an email to sarah@company.com", "DRAFT", "Explicit draft"),
        ("Send email to team@startup.com", "DRAFT", "Explicit send"),
        ("Create an email for the client", "DRAFT", "Creation request"),
        ("Compose a message to my boss", "DRAFT", "Compose request"),
        ("I need to email John about the project", "DRAFT", "Implicit email creation"),
    ]

    results = []
    passed = 0
    failed = 0

    for i, (query, expected, category) in enumerate(test_cases, 1):
        print(f"\n[{i:2d}/{len(test_cases)}] {category}")
        print(f"        Query: '{query}'")
        print(f"        Expected: {expected}")

        try:
            response = agency.get_completion(query)

            # Analyze response
            actual, is_correct, reasoning = analyze_response(response, expected)

            if is_correct:
                print(f"        ✅ PASS - Routed to {actual}")
                print(f"        {reasoning}")
                passed += 1
                results.append({
                    "test": i,
                    "query": query,
                    "expected": expected,
                    "actual": actual,
                    "status": "PASS",
                    "reasoning": reasoning
                })
            else:
                print(f"        ❌ FAIL - Expected {expected}, got {actual}")
                print(f"        {reasoning}")
                print(f"        Response preview: {response[:150]}...")
                failed += 1
                results.append({
                    "test": i,
                    "query": query,
                    "expected": expected,
                    "actual": actual,
                    "status": "FAIL",
                    "reasoning": reasoning,
                    "response": response[:300]
                })

        except Exception as e:
            print(f"        ❌ ERROR: {str(e)}")
            failed += 1
            results.append({
                "test": i,
                "query": query,
                "expected": expected,
                "status": "ERROR",
                "error": str(e)
            })

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    total = len(test_cases)
    success_rate = (passed / total * 100) if total > 0 else 0

    print(f"Total Tests: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"Success Rate: {success_rate:.1f}%")
    print()

    # Category breakdown
    fetch_tests = [r for r in results if r.get("expected") == "FETCH"]
    draft_tests = [r for r in results if r.get("expected") == "DRAFT"]

    fetch_passed = sum(1 for r in fetch_tests if r["status"] == "PASS")
    draft_passed = sum(1 for r in draft_tests if r["status"] == "PASS")

    print("Category Breakdown:")
    print(f"  FETCH operations: {fetch_passed}/{len(fetch_tests)} passed")
    print(f"  DRAFT operations: {draft_passed}/{len(draft_tests)} passed")
    print()

    if success_rate == 100:
        print("🎉 PASS: All intent routing tests passed!")
        print("✅ CEO correctly distinguishes fetch vs draft operations")
    elif success_rate >= 90:
        print("⚠️  WARNING: Most tests passed but some issues detected")
        print("Review failed cases above")
    else:
        print(f"💥 FAIL: Only {success_rate:.1f}% success rate")
        print("❌ Intent routing needs attention")

    # Show failed cases
    failed_cases = [r for r in results if r["status"] == "FAIL"]
    if failed_cases:
        print("\n" + "-" * 80)
        print("FAILED CASES:")
        print("-" * 80)
        for case in failed_cases:
            print(f"\nQuery: '{case['query']}'")
            print(f"Expected: {case['expected']} | Actual: {case['actual']}")
            print(f"Reasoning: {case['reasoning']}")
            if "response" in case:
                print(f"Response: {case['response'][:200]}...")

    print("\n" + "=" * 80)
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "success_rate": success_rate,
        "passed_test": success_rate == 100
    }


if __name__ == "__main__":
    result = test_intent_routing()
    exit(0 if result["passed_test"] else 1)

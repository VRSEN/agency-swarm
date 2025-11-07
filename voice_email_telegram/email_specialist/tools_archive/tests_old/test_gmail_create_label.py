#!/usr/bin/env python3
"""
Test script for GmailCreateLabel tool.
Tests label creation with various configurations and validates responses.
"""
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from email_specialist.tools.GmailCreateLabel import GmailCreateLabel


def test_basic_label_creation():
    """Test creating a basic label with default settings."""
    print("\n" + "=" * 60)
    print("TEST 1: Basic Label Creation")
    print("=" * 60)

    tool = GmailCreateLabel(name="TestBasicLabel")
    result = tool.run()

    try:
        data = json.loads(result)
        print(json.dumps(data, indent=2))

        if data.get("success"):
            print("\n✅ SUCCESS: Label created successfully")
            print(f"   Label ID: {data.get('label_id')}")
            print(f"   Name: {data.get('name')}")
            print(f"   Visibility: {data.get('label_list_visibility')}")
            return True
        else:
            print(f"\n❌ FAILED: {data.get('error')}")
            return False
    except json.JSONDecodeError:
        print("\n❌ FAILED: Invalid JSON response")
        print(result)
        return False


def test_hidden_label():
    """Test creating a label hidden from sidebar."""
    print("\n" + "=" * 60)
    print("TEST 2: Hidden Label (Auto-Archive)")
    print("=" * 60)

    tool = GmailCreateLabel(
        name="TestHiddenLabel",
        label_list_visibility="labelHide",
        message_list_visibility="hide"
    )
    result = tool.run()

    try:
        data = json.loads(result)
        print(json.dumps(data, indent=2))

        if data.get("success"):
            print("\n✅ SUCCESS: Hidden label created")
            print(f"   Label ID: {data.get('label_id')}")
            print(f"   Sidebar: {data.get('label_list_visibility')}")
            print(f"   Messages: {data.get('message_list_visibility')}")
            return True
        else:
            print(f"\n❌ FAILED: {data.get('error')}")
            return False
    except json.JSONDecodeError:
        print("\n❌ FAILED: Invalid JSON response")
        print(result)
        return False


def test_hierarchical_label():
    """Test creating a hierarchical label (nested)."""
    print("\n" + "=" * 60)
    print("TEST 3: Hierarchical Label")
    print("=" * 60)

    tool = GmailCreateLabel(name="TestParent/TestChild")
    result = tool.run()

    try:
        data = json.loads(result)
        print(json.dumps(data, indent=2))

        if data.get("success"):
            print("\n✅ SUCCESS: Hierarchical label created")
            print(f"   Label ID: {data.get('label_id')}")
            print(f"   Full Name: {data.get('name')}")
            return True
        else:
            print(f"\n❌ FAILED: {data.get('error')}")
            return False
    except json.JSONDecodeError:
        print("\n❌ FAILED: Invalid JSON response")
        print(result)
        return False


def test_label_with_spaces():
    """Test creating a label with spaces in name."""
    print("\n" + "=" * 60)
    print("TEST 4: Label With Spaces")
    print("=" * 60)

    tool = GmailCreateLabel(name="Test Label With Spaces")
    result = tool.run()

    try:
        data = json.loads(result)
        print(json.dumps(data, indent=2))

        if data.get("success"):
            print("\n✅ SUCCESS: Label with spaces created")
            print(f"   Label ID: {data.get('label_id')}")
            print(f"   Name: {data.get('name')}")
            return True
        else:
            print(f"\n❌ FAILED: {data.get('error')}")
            return False
    except json.JSONDecodeError:
        print("\n❌ FAILED: Invalid JSON response")
        print(result)
        return False


def test_empty_name_error():
    """Test that empty label name produces error."""
    print("\n" + "=" * 60)
    print("TEST 5: Empty Name Error Handling")
    print("=" * 60)

    tool = GmailCreateLabel(name="")
    result = tool.run()

    try:
        data = json.loads(result)
        print(json.dumps(data, indent=2))

        if not data.get("success") and "empty" in data.get("error", "").lower():
            print("\n✅ SUCCESS: Correctly rejected empty name")
            return True
        else:
            print("\n❌ FAILED: Should reject empty name")
            return False
    except json.JSONDecodeError:
        print("\n❌ FAILED: Invalid JSON response")
        print(result)
        return False


def test_invalid_visibility_error():
    """Test that invalid visibility option produces error."""
    print("\n" + "=" * 60)
    print("TEST 6: Invalid Visibility Error Handling")
    print("=" * 60)

    tool = GmailCreateLabel(
        name="TestLabel",
        label_list_visibility="invalidOption"
    )
    result = tool.run()

    try:
        data = json.loads(result)
        print(json.dumps(data, indent=2))

        if not data.get("success") and "invalid" in data.get("error", "").lower():
            print("\n✅ SUCCESS: Correctly rejected invalid visibility")
            return True
        else:
            print("\n❌ FAILED: Should reject invalid visibility")
            return False
    except json.JSONDecodeError:
        print("\n❌ FAILED: Invalid JSON response")
        print(result)
        return False


def test_real_world_labels():
    """Test creating real-world use case labels."""
    print("\n" + "=" * 60)
    print("TEST 7: Real-World Use Cases")
    print("=" * 60)

    test_cases = [
        {
            "name": "Clients",
            "description": "Client communications"
        },
        {
            "name": "Invoices",
            "description": "Billing and invoices"
        },
        {
            "name": "Work/ProjectA",
            "description": "Work project hierarchy"
        },
        {
            "name": "Important Tasks",
            "description": "High priority items"
        }
    ]

    results = []
    for test_case in test_cases:
        print(f"\nCreating '{test_case['name']}' ({test_case['description']})...")

        tool = GmailCreateLabel(name=test_case["name"])
        result = tool.run()

        try:
            data = json.loads(result)
            if data.get("success"):
                print(f"   ✅ Created: {data.get('label_id')}")
                results.append(True)
            else:
                # Label might already exist from previous test
                if "already exists" in data.get("error", "").lower():
                    print("   ⚠️  Already exists (OK)")
                    results.append(True)
                else:
                    print(f"   ❌ Failed: {data.get('error')}")
                    results.append(False)
        except json.JSONDecodeError:
            print("   ❌ Invalid response")
            results.append(False)

    success_rate = sum(results) / len(results) * 100
    print(f"\n{'✅' if success_rate >= 75 else '❌'} Success Rate: {success_rate:.0f}% ({sum(results)}/{len(results)})")
    return success_rate >= 75


def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "=" * 60)
    print("GMAIL CREATE LABEL TOOL - COMPREHENSIVE TEST SUITE")
    print("=" * 60)

    tests = [
        ("Basic Label Creation", test_basic_label_creation),
        ("Hidden Label", test_hidden_label),
        ("Hierarchical Label", test_hierarchical_label),
        ("Label With Spaces", test_label_with_spaces),
        ("Empty Name Error", test_empty_name_error),
        ("Invalid Visibility Error", test_invalid_visibility_error),
        ("Real-World Use Cases", test_real_world_labels)
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ EXCEPTION in {test_name}: {str(e)}")
            results.append((test_name, False))

    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print("\n" + "=" * 60)
    print(f"OVERALL: {passed}/{total} tests passed ({passed/total*100:.0f}%)")
    print("=" * 60)

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
    elif passed >= total * 0.75:
        print("\n⚠️  MOST TESTS PASSED - Review failures")
    else:
        print("\n❌ MULTIPLE FAILURES - Tool needs fixes")

    return passed == total


if __name__ == "__main__":
    print("Starting GmailCreateLabel comprehensive test suite...")
    print("Requires: COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env")
    print("=" * 60)

    success = run_all_tests()

    print("\n" + "=" * 60)
    print("TOOL INFORMATION")
    print("=" * 60)
    print("\nGmailCreateLabel - Create custom Gmail labels")
    print("\nParameters:")
    print("  - name (required): Label name")
    print("  - label_list_visibility (optional): 'labelShow' or 'labelHide'")
    print("  - message_list_visibility (optional): 'show' or 'hide'")
    print("\nUse Cases:")
    print("  - 'Create a label for Clients'")
    print("  - 'Add an Invoices label'")
    print("  - 'Make a Work/ProjectA label'")
    print("\nReturns:")
    print("  - success: bool")
    print("  - label_id: str (use with GmailAddLabel)")
    print("  - name: str")
    print("  - visibility settings")
    print("\nRelated Tools:")
    print("  - GmailListLabels: List all labels")
    print("  - GmailAddLabel: Add label to messages")
    print("  - GmailRemoveLabel: Remove label from messages")

    sys.exit(0 if success else 1)

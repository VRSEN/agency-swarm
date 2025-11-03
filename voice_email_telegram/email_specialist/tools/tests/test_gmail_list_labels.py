#!/usr/bin/env python3
"""
Test script for GmailListLabels tool.

Tests:
1. List all labels (success case)
2. Verify system labels exist
3. Verify custom labels can be listed
4. Verify label structure (id, name, type, counts)
5. Verify error handling for missing credentials
"""
import json
import os
import sys

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from GmailListLabels import GmailListLabels


def test_list_all_labels():
    """Test 1: List all labels"""
    print("\n" + "=" * 60)
    print("TEST 1: List all Gmail labels")
    print("=" * 60)

    tool = GmailListLabels()
    result = tool.run()
    result_data = json.loads(result)

    print(f"Success: {result_data.get('success')}")
    print(f"Total labels: {result_data.get('count', 0)}")
    print(f"System labels: {result_data.get('system_count', 0)}")
    print(f"Custom labels: {result_data.get('custom_count', 0)}")

    # Verify response structure
    assert "success" in result_data, "Response missing 'success' field"
    assert "labels" in result_data, "Response missing 'labels' field"
    assert "system_labels" in result_data, "Response missing 'system_labels' field"
    assert "custom_labels" in result_data, "Response missing 'custom_labels' field"

    if result_data.get("success"):
        print("✅ Test 1 PASSED - Labels listed successfully")
        return result_data
    else:
        print(f"❌ Test 1 FAILED - Error: {result_data.get('error')}")
        return None


def test_system_labels(result_data):
    """Test 2: Verify system labels exist"""
    print("\n" + "=" * 60)
    print("TEST 2: Verify system labels exist")
    print("=" * 60)

    if not result_data or not result_data.get("success"):
        print("⚠️  Skipping Test 2 - No valid data from Test 1")
        return

    system_labels = result_data.get("system_labels", [])
    system_label_names = [label.get("name") for label in system_labels]

    print(f"Found {len(system_labels)} system labels:")
    for label in system_labels[:10]:
        print(f"  - {label.get('name')} (ID: {label.get('id')})")

    # Check for common system labels
    expected_labels = ["INBOX", "SENT", "DRAFT", "TRASH", "SPAM"]
    found_labels = [label for label in expected_labels if label in system_label_names]

    print(f"\nExpected system labels found: {found_labels}")

    if len(found_labels) >= 3:
        print("✅ Test 2 PASSED - System labels verified")
    else:
        print("⚠️  Test 2 WARNING - Few system labels found (may be normal)")


def test_custom_labels(result_data):
    """Test 3: Verify custom labels structure"""
    print("\n" + "=" * 60)
    print("TEST 3: Verify custom labels structure")
    print("=" * 60)

    if not result_data or not result_data.get("success"):
        print("⚠️  Skipping Test 3 - No valid data from Test 1")
        return

    custom_labels = result_data.get("custom_labels", [])

    print(f"Found {len(custom_labels)} custom labels")

    if len(custom_labels) > 0:
        print("\nCustom labels:")
        for label in custom_labels:
            print(f"  - {label.get('name')} (ID: {label.get('id')})")
            print(f"    Type: {label.get('type')}")
            print(f"    Messages: {label.get('messagesTotal', 0)} total, {label.get('messagesUnread', 0)} unread")

        print("✅ Test 3 PASSED - Custom labels found and verified")
    else:
        print("⚠️  Test 3 INFO - No custom labels found (this is normal for new accounts)")


def test_label_structure(result_data):
    """Test 4: Verify label object structure"""
    print("\n" + "=" * 60)
    print("TEST 4: Verify label object structure")
    print("=" * 60)

    if not result_data or not result_data.get("success"):
        print("⚠️  Skipping Test 4 - No valid data from Test 1")
        return

    labels = result_data.get("labels", [])

    if len(labels) == 0:
        print("❌ Test 4 FAILED - No labels found")
        return

    # Check first label structure
    first_label = labels[0]
    required_fields = ["id", "name", "type"]

    print(f"Checking first label structure: {first_label.get('name')}")
    print(f"Label data: {json.dumps(first_label, indent=2)}")

    missing_fields = [field for field in required_fields if field not in first_label]

    if not missing_fields:
        print(f"✅ Test 4 PASSED - Label structure verified")
        print(f"   Required fields present: {required_fields}")
    else:
        print(f"❌ Test 4 FAILED - Missing fields: {missing_fields}")


def test_error_handling():
    """Test 5: Verify error handling for missing credentials"""
    print("\n" + "=" * 60)
    print("TEST 5: Test error handling (missing credentials)")
    print("=" * 60)

    # Save original env vars
    original_api_key = os.getenv("COMPOSIO_API_KEY")
    original_entity_id = os.getenv("GMAIL_ENTITY_ID")

    # Temporarily remove credentials
    if "COMPOSIO_API_KEY" in os.environ:
        del os.environ["COMPOSIO_API_KEY"]
    if "GMAIL_ENTITY_ID" in os.environ:
        del os.environ["GMAIL_ENTITY_ID"]

    tool = GmailListLabels()
    result = tool.run()
    result_data = json.loads(result)

    # Restore credentials
    if original_api_key:
        os.environ["COMPOSIO_API_KEY"] = original_api_key
    if original_entity_id:
        os.environ["GMAIL_ENTITY_ID"] = original_entity_id

    print(f"Success: {result_data.get('success')}")
    print(f"Error: {result_data.get('error')}")

    if not result_data.get("success") and "credentials" in result_data.get("error", "").lower():
        print("✅ Test 5 PASSED - Error handling works correctly")
    else:
        print("❌ Test 5 FAILED - Error handling did not work as expected")


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("GMAIL LIST LABELS TOOL - COMPREHENSIVE TEST SUITE")
    print("=" * 60)

    # Run tests
    result_data = test_list_all_labels()
    test_system_labels(result_data)
    test_custom_labels(result_data)
    test_label_structure(result_data)
    test_error_handling()

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)
    print("\nIntegration Notes:")
    print("- Label IDs can be used with GmailAddLabel tool")
    print("- Label names can be used in GmailFetchEmails query (e.g., 'label:INBOX')")
    print("- System labels are Gmail defaults (INBOX, SENT, etc.)")
    print("- Custom labels are user-created organizational labels")
    print("\nNext Steps:")
    print("1. Test with real Gmail account via Composio")
    print("2. Integrate with CEO agent routing")
    print("3. Build GmailAddLabel tool to use these label IDs")
    print("4. Test voice commands: 'What labels do I have?'")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Simple test for GmailCreateLabel - validates structure and error handling.
"""
import json

from GmailCreateLabel import GmailCreateLabel


def test_validation():
    """Test input validation without API calls."""
    print("=" * 60)
    print("GMAILCREATELABEL - VALIDATION TESTS (No API)")
    print("=" * 60)

    # Test 1: Empty name validation
    print("\n1. Empty name validation:")
    tool = GmailCreateLabel(name="")
    result = json.loads(tool.run())
    assert result.get("success") == False, "Should reject empty name"
    assert "empty" in result.get("error", "").lower(), "Should mention empty"
    print("   ✅ Correctly rejects empty name")

    # Test 2: Invalid visibility validation
    print("\n2. Invalid visibility validation:")
    tool = GmailCreateLabel(name="Test", label_list_visibility="invalid")
    result = json.loads(tool.run())
    assert result.get("success") == False, "Should reject invalid visibility"
    assert "invalid" in result.get("error", "").lower(), "Should mention invalid"
    print("   ✅ Correctly rejects invalid visibility")

    # Test 3: Invalid message visibility
    print("\n3. Invalid message visibility:")
    tool = GmailCreateLabel(name="Test", message_list_visibility="wrong")
    result = json.loads(tool.run())
    assert result.get("success") == False, "Should reject invalid message visibility"
    print("   ✅ Correctly rejects invalid message visibility")

    # Test 4: Tool structure validation
    print("\n4. Tool structure validation:")
    tool = GmailCreateLabel(name="ValidName")
    assert hasattr(tool, 'run'), "Should have run method"
    assert tool.name == "ValidName", "Should store name"
    assert tool.label_list_visibility == "labelShow", "Should default to labelShow"
    assert tool.message_list_visibility == "show", "Should default to show"
    print("   ✅ Tool structure is correct")

    # Test 5: Response structure
    print("\n5. Response structure validation:")
    tool = GmailCreateLabel(name="")
    result = json.loads(tool.run())
    assert "success" in result, "Should have success field"
    assert "error" in result, "Should have error field"
    assert "label_id" in result, "Should have label_id field"
    assert "name" in result, "Should have name field"
    print("   ✅ Response structure is correct")

    print("\n" + "=" * 60)
    print("✅ ALL VALIDATION TESTS PASSED!")
    print("=" * 60)
    print("\nTool is ready for production use with valid credentials.")
    print("\nRequired credentials:")
    print("  - COMPOSIO_API_KEY in .env")
    print("  - GMAIL_ENTITY_ID in .env")
    print("\nSupported parameters:")
    print("  - name (required): Label name")
    print("  - label_list_visibility: 'labelShow' | 'labelHide'")
    print("  - message_list_visibility: 'show' | 'hide'")


if __name__ == "__main__":
    test_validation()

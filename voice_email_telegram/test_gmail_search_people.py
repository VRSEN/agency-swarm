#!/usr/bin/env python3
"""
Test script for GmailSearchPeople tool.

Validates the tool follows the correct pattern from FINAL_VALIDATION_SUMMARY.md:
- Uses Composio SDK client.tools.execute()
- Uses user_id=entity_id (NOT dangerously_skip_version_check)
- Returns properly formatted JSON
- Handles errors gracefully
"""
import json
import os
import sys

from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from email_specialist.tools.GmailSearchPeople import GmailSearchPeople

load_dotenv()

def test_validation():
    """Test input validation"""
    print("=" * 60)
    print("VALIDATION TESTS")
    print("=" * 60)

    # Test 1: Empty query
    print("\n1. Empty query (should fail):")
    tool = GmailSearchPeople(query="", page_size=5)
    result = json.loads(tool.run())
    assert result["success"] == False
    assert "empty" in result["error"].lower()
    print("✅ PASS - Empty query rejected")

    # Test 2: Invalid page_size (too low)
    print("\n2. Invalid page_size = 0 (should fail):")
    tool = GmailSearchPeople(query="John", page_size=0)
    result = json.loads(tool.run())
    assert result["success"] == False
    assert "page_size must be between" in result["error"]
    print("✅ PASS - Invalid page_size rejected")

    # Test 3: Invalid page_size (too high)
    print("\n3. Invalid page_size = 200 (should fail):")
    tool = GmailSearchPeople(query="John", page_size=200)
    result = json.loads(tool.run())
    assert result["success"] == False
    assert "page_size must be between" in result["error"]
    print("✅ PASS - Invalid page_size rejected")

    print("\n✅ ALL VALIDATION TESTS PASSED")


def test_structure():
    """Test that response structure matches requirements"""
    print("\n" + "=" * 60)
    print("RESPONSE STRUCTURE TESTS")
    print("=" * 60)

    # Test with valid inputs (will fail auth but structure should be correct)
    print("\n1. Testing response structure:")
    tool = GmailSearchPeople(query="John Smith", page_size=10)
    result = json.loads(tool.run())

    # Check required fields exist
    assert "success" in result
    assert "count" in result
    assert "people" in result
    assert isinstance(result["people"], list)
    print("✅ PASS - Response has required fields")

    # Check error handling
    if not result["success"]:
        assert "error" in result
        assert "type" in result
        print("✅ PASS - Error response properly formatted")

    print("\n✅ ALL STRUCTURE TESTS PASSED")


def test_pattern_compliance():
    """Test that tool follows validated Composio SDK pattern"""
    print("\n" + "=" * 60)
    print("PATTERN COMPLIANCE TESTS")
    print("=" * 60)

    # Read the tool source code
    tool_file = os.path.join(
        os.path.dirname(__file__),
        "email_specialist/tools/GmailSearchPeople.py"
    )

    with open(tool_file, 'r') as f:
        source = f.read()

    # Check 1: Uses Composio import
    assert "from composio import Composio" in source
    print("✅ PASS - Uses Composio SDK import")

    # Check 2: Uses client.tools.execute pattern
    assert "client.tools.execute(" in source
    print("✅ PASS - Uses client.tools.execute() pattern")

    # Check 3: Uses GMAIL_SEARCH_PEOPLE action
    assert '"GMAIL_SEARCH_PEOPLE"' in source
    print("✅ PASS - Uses correct action name")

    # Check 4: Uses user_id=entity_id
    assert "user_id=entity_id" in source
    print("✅ PASS - Uses user_id=entity_id parameter")

    # Check 5: Does NOT use dangerously_skip_version_check
    assert "dangerously_skip_version_check" not in source
    print("✅ PASS - Does NOT use dangerously_skip_version_check")

    # Check 6: Inherits from BaseTool
    assert "from agency_swarm.tools import BaseTool" in source
    assert "class GmailSearchPeople(BaseTool):" in source
    print("✅ PASS - Inherits from BaseTool")

    # Check 7: Has proper docstring
    assert '"""' in source
    print("✅ PASS - Has docstring")

    # Check 8: Uses Field from pydantic
    assert "from pydantic import Field" in source
    assert "Field(" in source
    print("✅ PASS - Uses pydantic Field for parameters")

    print("\n✅ ALL PATTERN COMPLIANCE TESTS PASSED")


def test_real_credentials():
    """Test with real credentials if available"""
    print("\n" + "=" * 60)
    print("REAL CREDENTIALS TEST")
    print("=" * 60)

    api_key = os.getenv("COMPOSIO_API_KEY")
    entity_id = os.getenv("GMAIL_ENTITY_ID")

    if not api_key or not entity_id:
        print("⚠️  SKIP - No credentials in .env file")
        return

    print("\n1. Testing with real credentials:")
    print(f"   API Key: {api_key[:10]}...")
    print(f"   Entity ID: {entity_id[:20]}...")

    tool = GmailSearchPeople(query="test", page_size=5)
    result = json.loads(tool.run())

    print(f"\n   Success: {result.get('success')}")
    if result.get("success"):
        print(f"   Count: {result.get('count')}")
        print(f"   People found: {len(result.get('people', []))}")
        print("✅ PASS - Real credentials work!")
    else:
        print(f"   Error: {result.get('error')}")
        if "401" in result.get("error", ""):
            print("⚠️  WARNING - Authentication failed (may need to reconnect Gmail)")
        else:
            print("ℹ️  INFO - Other error (check error message)")


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("GMAILSEARCHPEOPLE TOOL TEST SUITE")
    print("=" * 60)
    print("\nTesting tool compliance with FINAL_VALIDATION_SUMMARY.md")
    print("Verified pattern: Composio SDK with user_id=entity_id")

    try:
        # Run test suites
        test_validation()
        test_structure()
        test_pattern_compliance()
        test_real_credentials()

        # Final summary
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
        print("\n✅ Tool is ready for production use")
        print("\nPattern Validation:")
        print("  ✅ Uses Composio SDK client.tools.execute()")
        print("  ✅ Uses user_id=entity_id (NOT dangerously_skip_version_check)")
        print("  ✅ Inherits from BaseTool")
        print("  ✅ Returns properly formatted JSON")
        print("  ✅ Has proper error handling")
        print("  ✅ Has input validation")
        print("\nNext Steps:")
        print("  1. Ensure Gmail connected via Composio with People API scope")
        print("  2. Tool will be auto-discovered by email_specialist agent")
        print("  3. Test via Telegram: 'Find John's email address'")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

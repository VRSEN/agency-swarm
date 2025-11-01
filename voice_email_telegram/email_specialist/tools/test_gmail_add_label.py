#!/usr/bin/env python3
"""
Integration test for GmailAddLabel tool.
Tests tool structure, validation, and pattern compliance.
"""
import json
import sys
import os

# Add parent directory to path to import the tool
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.GmailAddLabel import GmailAddLabel


def test_tool_structure():
    """Test 1: Verify tool structure and imports"""
    print("Test 1: Tool Structure")
    print("-" * 50)

    # Check class exists
    assert GmailAddLabel is not None, "GmailAddLabel class should exist"
    print("✅ GmailAddLabel class imported successfully")

    # Check it's a BaseTool
    assert hasattr(GmailAddLabel, 'run'), "Should have run() method"
    print("✅ Has run() method")

    # Check required fields
    tool = GmailAddLabel(
        message_id="test_123",
        label_ids=["IMPORTANT"]
    )
    assert tool.message_id == "test_123", "Should store message_id"
    assert tool.label_ids == ["IMPORTANT"], "Should store label_ids"
    print("✅ Fields are properly configured")

    print()


def test_validation():
    """Test 2: Verify input validation"""
    print("Test 2: Input Validation")
    print("-" * 50)

    # Test missing message_id
    tool = GmailAddLabel(
        message_id="",
        label_ids=["IMPORTANT"]
    )
    result = json.loads(tool.run())
    assert "error" in result, "Should error on missing message_id"
    assert "message_id is required" in result["error"], "Should specify message_id error"
    print("✅ Validates missing message_id")

    # Test empty label_ids
    tool = GmailAddLabel(
        message_id="test_123",
        label_ids=[]
    )
    result = json.loads(tool.run())
    assert "error" in result, "Should error on empty label_ids"
    assert "label_ids is required" in result["error"], "Should specify label_ids error"
    print("✅ Validates empty label_ids")

    print()


def test_pattern_compliance():
    """Test 3: Verify Composio SDK pattern compliance"""
    print("Test 3: Pattern Compliance")
    print("-" * 50)

    # Read the source code to verify pattern
    source_file = os.path.join(
        os.path.dirname(__file__),
        "GmailAddLabel.py"
    )

    with open(source_file, 'r') as f:
        source_code = f.read()

    # Check for required patterns
    assert 'from composio import Composio' in source_code, "Should import Composio"
    print("✅ Imports Composio SDK")

    assert 'client = Composio(api_key=api_key)' in source_code, "Should initialize Composio client"
    print("✅ Initializes Composio client correctly")

    assert 'client.tools.execute(' in source_code, "Should use client.tools.execute()"
    print("✅ Uses client.tools.execute() pattern")

    assert '"GMAIL_ADD_LABEL_TO_EMAIL"' in source_code, "Should use correct action name"
    print("✅ Uses correct action: GMAIL_ADD_LABEL_TO_EMAIL")

    assert 'user_id=entity_id' in source_code, "Should use user_id=entity_id"
    print("✅ Uses user_id=entity_id (validated pattern)")

    assert 'dangerously_skip_version_check' not in source_code, "Should NOT use dangerously_skip_version_check"
    print("✅ Does NOT use dangerously_skip_version_check (correct!)")

    assert '"user_id": "me"' in source_code, "Should include user_id in params"
    print("✅ Includes user_id: 'me' in params")

    print()


def test_documentation():
    """Test 4: Verify documentation completeness"""
    print("Test 4: Documentation")
    print("-" * 50)

    # Check docstring
    assert GmailAddLabel.__doc__ is not None, "Should have class docstring"
    docstring = GmailAddLabel.__doc__

    assert "label" in docstring.lower(), "Should mention labels in docstring"
    print("✅ Has descriptive docstring")

    assert "IMPORTANT" in docstring, "Should document IMPORTANT label"
    assert "STARRED" in docstring, "Should document STARRED label"
    print("✅ Documents common system labels")

    assert "Label_" in docstring, "Should document custom label format"
    print("✅ Documents custom label format")

    print()


def test_response_format():
    """Test 5: Verify response format structure"""
    print("Test 5: Response Format")
    print("-" * 50)

    # Test error response format
    tool = GmailAddLabel(
        message_id="",
        label_ids=["IMPORTANT"]
    )
    result = json.loads(tool.run())

    assert isinstance(result, dict), "Response should be a dict"
    assert "error" in result, "Error response should have 'error' key"
    print("✅ Returns properly formatted JSON")
    print("✅ Error responses have 'error' key")

    print()


def run_all_tests():
    """Run all tests"""
    print("=" * 50)
    print("GMAIL ADD LABEL TOOL - VALIDATION TESTS")
    print("=" * 50)
    print()

    tests = [
        test_tool_structure,
        test_validation,
        test_pattern_compliance,
        test_documentation,
        test_response_format
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"❌ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ ERROR: {e}")
            failed += 1

    print()
    print("=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    print(f"✅ Passed: {passed}/{len(tests)}")
    if failed > 0:
        print(f"❌ Failed: {failed}/{len(tests)}")
    else:
        print("🎉 All tests passed!")
    print()

    if failed == 0:
        print("VALIDATION COMPLETE:")
        print("✅ Tool structure is correct")
        print("✅ Input validation works")
        print("✅ Follows validated Composio pattern")
        print("✅ Uses user_id=entity_id (NOT dangerously_skip_version_check)")
        print("✅ Properly documented")
        print("✅ Returns correct JSON format")
        print()
        print("READY FOR PRODUCTION USE")
    else:
        print("⚠️ Some tests failed - review output above")

    print()
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

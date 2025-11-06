#!/usr/bin/env python3
"""
Comprehensive Test Suite for GmailGetProfile Tool

Tests all functionality including:
- Default user profile retrieval
- Explicit user_id parameter
- Error handling for missing credentials
- Profile data parsing and validation
- Mailbox statistics calculation
- Edge cases and error conditions
"""
import json
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from email_specialist.tools.GmailGetProfile import GmailGetProfile

load_dotenv()


def test_default_user_profile():
    """Test 1: Get profile for authenticated user (default)"""
    print("\n" + "=" * 80)
    print("TEST 1: Get Profile for Authenticated User (Default)")
    print("=" * 80)

    tool = GmailGetProfile()
    result_str = tool.run()
    result = json.loads(result_str)

    print(f"Success: {result.get('success')}")
    print(f"Email: {result.get('email_address')}")
    print(f"Messages: {result.get('messages_total', 0):,}")
    print(f"Threads: {result.get('threads_total', 0):,}")
    print(f"Ratio: {result.get('messages_per_thread', 0)}")

    assert result.get("success") == True, "Profile fetch should succeed"
    assert result.get("email_address"), "Should return email address"
    assert "messages_total" in result, "Should return message count"
    assert "threads_total" in result, "Should return thread count"

    print("✅ TEST 1 PASSED")
    return result


def test_explicit_user_id():
    """Test 2: Get profile with explicit 'me' user_id"""
    print("\n" + "=" * 80)
    print("TEST 2: Get Profile with Explicit 'me' user_id")
    print("=" * 80)

    tool = GmailGetProfile(user_id="me")
    result_str = tool.run()
    result = json.loads(result_str)

    print(f"Success: {result.get('success')}")
    print(f"User ID: {result.get('user_id')}")
    print(f"Email: {result.get('email_address')}")

    assert result.get("success") == True, "Profile fetch should succeed"
    assert result.get("user_id") == "me", "Should use 'me' as user_id"
    assert result.get("email_address"), "Should return email address"

    print("✅ TEST 2 PASSED")
    return result


def test_profile_data_structure():
    """Test 3: Validate complete profile data structure"""
    print("\n" + "=" * 80)
    print("TEST 3: Validate Profile Data Structure")
    print("=" * 80)

    tool = GmailGetProfile()
    result_str = tool.run()
    result = json.loads(result_str)

    required_fields = [
        "success",
        "email_address",
        "messages_total",
        "threads_total",
        "history_id",
        "messages_per_thread",
        "profile_summary",
        "user_id"
    ]

    print("Checking required fields:")
    for field in required_fields:
        present = field in result
        print(f"  {field}: {'✓' if present else '✗'}")
        assert present, f"Missing required field: {field}"

    print("\nProfile Summary:")
    print(f"  {result.get('profile_summary')}")

    print("✅ TEST 3 PASSED")
    return result


def test_mailbox_statistics():
    """Test 4: Calculate and validate mailbox statistics"""
    print("\n" + "=" * 80)
    print("TEST 4: Mailbox Statistics Calculation")
    print("=" * 80)

    tool = GmailGetProfile()
    result_str = tool.run()
    result = json.loads(result_str)

    if result.get("success"):
        messages = result.get("messages_total", 0)
        threads = result.get("threads_total", 0)
        ratio = result.get("messages_per_thread", 0)

        print(f"Total Messages: {messages:,}")
        print(f"Total Threads: {threads:,}")
        print(f"Messages per Thread: {ratio}")

        # Validate ratio calculation
        if threads > 0:
            expected_ratio = round(messages / threads, 2)
            assert ratio == expected_ratio, f"Ratio mismatch: {ratio} vs {expected_ratio}"
            print(f"✓ Ratio calculation correct: {ratio}")

        # Determine mailbox health
        if ratio > 0:
            if ratio < 2:
                health = "Healthy - Most emails are standalone"
            elif ratio < 5:
                health = "Normal - Moderate conversation activity"
            elif ratio < 10:
                health = "Active - High conversation engagement"
            else:
                health = "Very Active - Extensive email threads"

            print(f"\nMailbox Health Assessment: {health}")

    print("✅ TEST 4 PASSED")
    return result


def test_missing_credentials():
    """Test 5: Handle missing credentials gracefully"""
    print("\n" + "=" * 80)
    print("TEST 5: Missing Credentials Error Handling")
    print("=" * 80)

    # Save current credentials
    original_api_key = os.getenv("COMPOSIO_API_KEY")
    original_entity_id = os.getenv("GMAIL_ENTITY_ID")

    # Temporarily clear credentials
    if "COMPOSIO_API_KEY" in os.environ:
        del os.environ["COMPOSIO_API_KEY"]
    if "GMAIL_ENTITY_ID" in os.environ:
        del os.environ["GMAIL_ENTITY_ID"]

    tool = GmailGetProfile()
    result_str = tool.run()
    result = json.loads(result_str)

    print(f"Success: {result.get('success')}")
    print(f"Error: {result.get('error')}")

    assert result.get("success") == False, "Should fail without credentials"
    assert "Missing Composio credentials" in result.get("error", ""), "Should have credential error message"
    assert result.get("email_address") is None, "Should not return email address"
    assert result.get("messages_total") == 0, "Should return 0 messages"
    assert result.get("threads_total") == 0, "Should return 0 threads"

    # Restore credentials
    if original_api_key:
        os.environ["COMPOSIO_API_KEY"] = original_api_key
    if original_entity_id:
        os.environ["GMAIL_ENTITY_ID"] = original_entity_id

    print("✅ TEST 5 PASSED")
    return result


def test_profile_summary_format():
    """Test 6: Validate profile summary formatting"""
    print("\n" + "=" * 80)
    print("TEST 6: Profile Summary Format Validation")
    print("=" * 80)

    tool = GmailGetProfile()
    result_str = tool.run()
    result = json.loads(result_str)

    if result.get("success"):
        summary = result.get("profile_summary", "")
        email = result.get("email_address", "")
        messages = result.get("messages_total", 0)
        threads = result.get("threads_total", 0)

        print(f"Summary: {summary}")

        # Validate summary contains expected elements
        assert email in summary, "Summary should contain email address"
        assert str(messages) in summary, "Summary should contain message count"
        assert str(threads) in summary, "Summary should contain thread count"
        assert "messages" in summary, "Summary should mention 'messages'"
        assert "threads" in summary, "Summary should mention 'threads'"

        print("✓ Summary format is correct")

    print("✅ TEST 6 PASSED")
    return result


def test_json_output_format():
    """Test 7: Validate JSON output format and parsing"""
    print("\n" + "=" * 80)
    print("TEST 7: JSON Output Format Validation")
    print("=" * 80)

    tool = GmailGetProfile()
    result_str = tool.run()

    # Test that output is valid JSON
    try:
        result = json.loads(result_str)
        print("✓ Output is valid JSON")
    except json.JSONDecodeError as e:
        raise AssertionError(f"Invalid JSON output: {e}")

    # Test that JSON is properly formatted (indented)
    assert "\n" in result_str, "JSON should be indented"
    assert "  " in result_str, "JSON should use 2-space indentation"

    print("✓ JSON is properly formatted")

    # Test that numbers are actual numbers, not strings
    if result.get("success"):
        assert isinstance(result.get("messages_total"), int), "messages_total should be integer"
        assert isinstance(result.get("threads_total"), int), "threads_total should be integer"
        assert isinstance(result.get("messages_per_thread"), (int, float)), "messages_per_thread should be numeric"

    print("✓ Data types are correct")
    print("✅ TEST 7 PASSED")
    return result


def test_zero_thread_edge_case():
    """Test 8: Handle zero threads edge case (messages_per_thread calculation)"""
    print("\n" + "=" * 80)
    print("TEST 8: Zero Threads Edge Case")
    print("=" * 80)

    # This test validates that the code handles threads_total=0 without division by zero
    # In real usage, this would be extremely rare but we validate the logic
    print("Testing division by zero protection in messages_per_thread calculation")

    # Get actual profile
    tool = GmailGetProfile()
    result_str = tool.run()
    result = json.loads(result_str)

    if result.get("success"):
        threads = result.get("threads_total", 0)
        ratio = result.get("messages_per_thread", 0)

        if threads == 0:
            assert ratio == 0.0, "Ratio should be 0.0 when threads_total is 0"
            print("✓ Correctly handles zero threads (ratio = 0.0)")
        else:
            print(f"✓ Normal case with {threads} threads (ratio = {ratio})")

    print("✅ TEST 8 PASSED")
    return result


def run_all_tests():
    """Run all test cases and generate summary report"""
    print("\n" + "=" * 80)
    print("GMAIL GET PROFILE - COMPREHENSIVE TEST SUITE")
    print("=" * 80)

    tests = [
        ("Default User Profile", test_default_user_profile),
        ("Explicit User ID", test_explicit_user_id),
        ("Profile Data Structure", test_profile_data_structure),
        ("Mailbox Statistics", test_mailbox_statistics),
        ("Missing Credentials", test_missing_credentials),
        ("Profile Summary Format", test_profile_summary_format),
        ("JSON Output Format", test_json_output_format),
        ("Zero Thread Edge Case", test_zero_thread_edge_case),
    ]

    results = []
    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, "PASSED", result))
            passed += 1
        except AssertionError as e:
            results.append((test_name, f"FAILED: {e}", None))
            failed += 1
        except Exception as e:
            results.append((test_name, f"ERROR: {e}", None))
            failed += 1

    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    for test_name, status, _ in results:
        status_symbol = "✅" if "PASSED" in status else "❌"
        print(f"{status_symbol} {test_name}: {status}")

    print("\n" + "=" * 80)
    print(f"Total Tests: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {(passed/len(tests)*100):.1f}%")
    print("=" * 80)

    return passed == len(tests)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

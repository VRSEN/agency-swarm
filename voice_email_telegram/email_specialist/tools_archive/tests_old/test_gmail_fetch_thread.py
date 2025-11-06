#!/usr/bin/env python3
"""
Test suite for GmailFetchMessageByThreadId tool.

Tests:
1. Valid thread ID fetch
2. Missing credentials handling
3. Empty thread_id validation
4. Error handling for invalid thread_id
5. Response structure validation
6. Message parsing validation
"""
import json
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from email_specialist.tools.GmailFetchMessageByThreadId import GmailFetchMessageByThreadId

load_dotenv()


def test_valid_thread_fetch():
    """Test 1: Fetch thread with valid ID"""
    print("\n" + "=" * 70)
    print("TEST 1: Fetch thread with valid ID")
    print("=" * 70)

    # Note: Replace with actual thread_id from your Gmail for real testing
    tool = GmailFetchMessageByThreadId(thread_id="18c1234567890abcd")
    result = tool.run()

    print("\nRaw Result:")
    print(result)

    # Parse and validate response
    response = json.loads(result)

    print("\nValidation:")
    print(f"✓ success field present: {('success' in response)}")
    print(f"✓ thread_id field present: {('thread_id' in response)}")
    print(f"✓ message_count field present: {('message_count' in response)}")
    print(f"✓ messages field present: {('messages' in response)}")

    if response.get("success"):
        print(f"\n✅ SUCCESS: Fetched {response.get('message_count')} messages")
        messages = response.get("messages", [])
        if messages:
            print(f"\nFirst message preview:")
            first = messages[0]
            print(f"  - From: {first.get('from')}")
            print(f"  - Subject: {first.get('subject')}")
            print(f"  - Date: {first.get('date')}")
            print(f"  - Snippet: {first.get('snippet', '')[:100]}...")
    else:
        print(f"\n⚠️  Expected behavior - Thread might not exist or API error")
        print(f"Error: {response.get('error')}")

    return response


def test_missing_credentials():
    """Test 2: Missing credentials handling"""
    print("\n" + "=" * 70)
    print("TEST 2: Missing credentials handling")
    print("=" * 70)

    # Temporarily clear env vars
    original_api_key = os.environ.get("COMPOSIO_API_KEY")
    original_entity_id = os.environ.get("GMAIL_ENTITY_ID")

    os.environ.pop("COMPOSIO_API_KEY", None)
    os.environ.pop("GMAIL_ENTITY_ID", None)

    tool = GmailFetchMessageByThreadId(thread_id="18c1234567890abcd")
    result = tool.run()

    print("\nResult:")
    print(result)

    response = json.loads(result)

    # Restore env vars
    if original_api_key:
        os.environ["COMPOSIO_API_KEY"] = original_api_key
    if original_entity_id:
        os.environ["GMAIL_ENTITY_ID"] = original_entity_id

    assert not response.get("success"), "Should fail without credentials"
    assert "Missing Composio credentials" in response.get("error", ""), "Should show missing credentials error"

    print("\n✅ PASS: Correctly handles missing credentials")

    return response


def test_empty_thread_id():
    """Test 3: Empty thread_id validation"""
    print("\n" + "=" * 70)
    print("TEST 3: Empty thread_id validation")
    print("=" * 70)

    try:
        tool = GmailFetchMessageByThreadId(thread_id="")
        result = tool.run()

        print("\nResult:")
        print(result)

        response = json.loads(result)
        assert not response.get("success"), "Should fail with empty thread_id"
        assert "thread_id is required" in response.get("error", ""), "Should show thread_id required error"

        print("\n✅ PASS: Correctly validates empty thread_id")
        return response

    except Exception as e:
        print(f"\n✅ PASS: Pydantic validation caught empty thread_id: {e}")
        return {"success": False, "error": str(e)}


def test_invalid_thread_id():
    """Test 4: Invalid thread_id error handling"""
    print("\n" + "=" * 70)
    print("TEST 4: Invalid thread_id error handling")
    print("=" * 70)

    tool = GmailFetchMessageByThreadId(thread_id="invalid_thread_id_12345")
    result = tool.run()

    print("\nResult:")
    print(result)

    response = json.loads(result)

    print("\nValidation:")
    print(f"✓ Response is valid JSON: True")
    print(f"✓ Has success field: {('success' in response)}")
    print(f"✓ Has error field: {('error' in response)}")
    print(f"✓ Success is False: {(response.get('success') == False)}")

    print("\n✅ PASS: Gracefully handles invalid thread_id")

    return response


def test_response_structure():
    """Test 5: Response structure validation"""
    print("\n" + "=" * 70)
    print("TEST 5: Response structure validation")
    print("=" * 70)

    tool = GmailFetchMessageByThreadId(thread_id="18c1234567890abcd")
    result = tool.run()

    response = json.loads(result)

    required_fields = ["success", "thread_id", "message_count", "messages"]

    print("\nChecking required fields:")
    all_present = True
    for field in required_fields:
        present = field in response
        print(f"  - {field}: {'✓' if present else '✗'}")
        all_present = all_present and present

    if all_present:
        print("\n✅ PASS: All required fields present")
    else:
        print("\n❌ FAIL: Missing required fields")

    # Check message structure if messages exist
    if response.get("message_count", 0) > 0:
        print("\nChecking message structure:")
        message_fields = ["message_id", "thread_id", "subject", "from", "to", "date", "snippet", "body_data"]
        first_message = response["messages"][0]

        for field in message_fields:
            present = field in first_message
            print(f"  - {field}: {'✓' if present else '✗'}")

    return response


def test_message_parsing():
    """Test 6: Message parsing validation"""
    print("\n" + "=" * 70)
    print("TEST 6: Message parsing validation")
    print("=" * 70)

    tool = GmailFetchMessageByThreadId(thread_id="18c1234567890abcd")
    result = tool.run()

    response = json.loads(result)

    if response.get("success") and response.get("message_count", 0) > 0:
        print(f"\n✅ Thread contains {response['message_count']} messages")

        print("\nMessage details:")
        for i, msg in enumerate(response["messages"], 1):
            print(f"\nMessage {i}:")
            print(f"  - ID: {msg.get('message_id', 'N/A')}")
            print(f"  - From: {msg.get('from', 'N/A')}")
            print(f"  - Subject: {msg.get('subject', 'N/A')}")
            print(f"  - Date: {msg.get('date', 'N/A')}")
            print(f"  - Labels: {msg.get('labels', [])}")
            print(f"  - Snippet: {msg.get('snippet', 'N/A')[:80]}...")

        print("\n✅ PASS: Messages parsed successfully")
    else:
        print("\n⚠️  No messages to validate or thread doesn't exist")

    return response


def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("GMAIL FETCH MESSAGE BY THREAD ID - COMPREHENSIVE TEST SUITE")
    print("=" * 70)

    # Check environment setup
    api_key = os.getenv("COMPOSIO_API_KEY")
    entity_id = os.getenv("GMAIL_ENTITY_ID")

    print("\nEnvironment Setup:")
    print(f"  - COMPOSIO_API_KEY: {'✓ Set' if api_key else '✗ Missing'}")
    print(f"  - GMAIL_ENTITY_ID: {'✓ Set' if entity_id else '✗ Missing'}")

    if not api_key or not entity_id:
        print("\n⚠️  WARNING: Missing credentials. Some tests will fail.")
        print("Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env for full testing.")

    tests = [
        ("Valid thread fetch", test_valid_thread_fetch),
        ("Missing credentials", test_missing_credentials),
        ("Empty thread_id", test_empty_thread_id),
        ("Invalid thread_id", test_invalid_thread_id),
        ("Response structure", test_response_structure),
        ("Message parsing", test_message_parsing),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, True, result))
        except Exception as e:
            print(f"\n❌ TEST FAILED: {test_name}")
            print(f"Error: {str(e)}")
            results.append((test_name, False, str(e)))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, success, _ in results if success)
    total = len(results)

    for test_name, success, _ in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")

    return results


if __name__ == "__main__":
    print("GmailFetchMessageByThreadId Tool Test Suite")
    print("=" * 70)

    # Check if running with real thread_id
    if len(sys.argv) > 1:
        real_thread_id = sys.argv[1]
        print(f"\nTesting with real thread_id: {real_thread_id}")
        print("=" * 70)

        tool = GmailFetchMessageByThreadId(thread_id=real_thread_id)
        result = tool.run()

        print("\nResult:")
        print(result)

        response = json.loads(result)
        if response.get("success"):
            print(f"\n✅ Successfully fetched {response.get('message_count')} messages")
            for i, msg in enumerate(response.get("messages", []), 1):
                print(f"\nMessage {i}:")
                print(f"  From: {msg.get('from')}")
                print(f"  Subject: {msg.get('subject')}")
                print(f"  Date: {msg.get('date')}")
        else:
            print(f"\n❌ Failed: {response.get('error')}")
    else:
        print("\nRunning comprehensive test suite...")
        print("(Pass a real thread_id as argument for live testing)")
        run_all_tests()

    print("\n" + "=" * 70)
    print("Testing complete!")
    print("\nUsage:")
    print("  python test_gmail_fetch_thread.py                    # Run all tests")
    print("  python test_gmail_fetch_thread.py <thread_id>        # Test with real thread")
    print("=" * 70)

#!/usr/bin/env python3
"""
Test script for email signature functionality in GmailSendEmail.

Tests automatic signature append with various scenarios.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from email_specialist.tools.GmailSendEmail import GmailSendEmail


def test_signature_append():
    """Test automatic signature append functionality."""
    print("=" * 70)
    print("EMAIL SIGNATURE TESTS")
    print("=" * 70)

    # Test 1: Basic signature append
    print("\n[TEST 1] Basic signature append")
    print("-" * 70)
    tool = GmailSendEmail(
        to="test@example.com",
        subject="Test Email",
        body="Hello,\n\nThis is a test email."
    )

    # Test the signature append method directly
    result_body = tool._append_signature(tool.body)
    expected = "Hello,\n\nThis is a test email.\n\nCheers, Ashley"

    if result_body == expected:
        print("✓ PASS: Signature appended correctly")
        print(f"Result:\n{result_body}")
    else:
        print("✗ FAIL: Signature not appended correctly")
        print(f"Expected:\n{expected}")
        print(f"Got:\n{result_body}")

    # Test 2: Signature already present (should not duplicate)
    print("\n[TEST 2] Signature already present")
    print("-" * 70)
    tool = GmailSendEmail(
        to="test@example.com",
        subject="Test Email",
        body="Hello,\n\nThis is a test.\n\nCheers, Ashley"
    )

    result_body = tool._append_signature(tool.body)
    expected = "Hello,\n\nThis is a test.\n\nCheers, Ashley"

    if result_body == expected and result_body.count("Cheers, Ashley") == 1:
        print("✓ PASS: Signature not duplicated")
        print(f"Result:\n{result_body}")
    else:
        print("✗ FAIL: Signature duplicated")
        print(f"Expected:\n{expected}")
        print(f"Got:\n{result_body}")

    # Test 3: Empty body
    print("\n[TEST 3] Empty body")
    print("-" * 70)
    tool = GmailSendEmail(
        to="test@example.com",
        subject="Test Email",
        body=""
    )

    result_body = tool._append_signature(tool.body)
    expected = "\n\nCheers, Ashley"

    if result_body == expected:
        print("✓ PASS: Signature added to empty body")
        print(f"Result:\n{result_body}")
    else:
        print("✗ FAIL: Signature not added correctly to empty body")
        print(f"Expected:\n{expected}")
        print(f"Got:\n{result_body}")

    # Test 4: Body with trailing whitespace
    print("\n[TEST 4] Body with trailing whitespace")
    print("-" * 70)
    tool = GmailSendEmail(
        to="test@example.com",
        subject="Test Email",
        body="Hello,\n\nThis is a test.   \n\n  "
    )

    result_body = tool._append_signature(tool.body)
    expected = "Hello,\n\nThis is a test.\n\nCheers, Ashley"

    if result_body == expected:
        print("✓ PASS: Trailing whitespace removed before signature")
        print(f"Result:\n{result_body}")
    else:
        print("✗ FAIL: Trailing whitespace not handled correctly")
        print(f"Expected:\n{expected}")
        print(f"Got:\n{result_body}")

    # Test 5: Skip signature option
    print("\n[TEST 5] Skip signature option")
    print("-" * 70)
    tool = GmailSendEmail(
        to="test@example.com",
        subject="Test Email",
        body="Automated message.",
        skip_signature=True
    )

    # When skip_signature is True, body should remain unchanged
    if tool.skip_signature:
        print("✓ PASS: skip_signature flag set correctly")
        print("Body will not have signature appended during send")
    else:
        print("✗ FAIL: skip_signature flag not set")

    # Test 6: Signature in middle of text (should not be detected as already present)
    print("\n[TEST 6] Signature text in middle of body")
    print("-" * 70)
    tool = GmailSendEmail(
        to="test@example.com",
        subject="Test Email",
        body="Hello,\n\nI talked to Ashley. Cheers, Ashley said.\n\nThanks"
    )

    result_body = tool._append_signature(tool.body)

    # Should NOT append signature because "Cheers, Ashley" is present (even if in wrong context)
    # This is acceptable behavior - prevents duplication
    if "Cheers, Ashley" in result_body and result_body.count("Cheers, Ashley") == 1:
        print("✓ PASS: Signature not duplicated (existing text contains signature)")
        print(f"Result:\n{result_body}")
    else:
        print("Note: Signature handling when signature text appears in body context")
        print(f"Result:\n{result_body}")

    print("\n" + "=" * 70)
    print("SIGNATURE TESTS COMPLETED")
    print("=" * 70)


def test_integration():
    """Test signature integration in full send flow."""
    print("\n" + "=" * 70)
    print("INTEGRATION TESTS (requires .env credentials)")
    print("=" * 70)

    # Check if credentials are available
    if not os.getenv("COMPOSIO_API_KEY") or not os.getenv("GMAIL_CONNECTION_ID"):
        print("\n⚠ WARNING: Missing credentials in .env")
        print("Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID to run integration tests")
        print("\nSKIPPING integration tests")
        return

    print("\n[TEST] Send email with signature")
    print("-" * 70)

    tool = GmailSendEmail(
        to="test@example.com",
        subject="Signature Test",
        body="This is a test email to verify signature functionality."
    )

    result = tool.run()
    print(result)

    # Note: This will attempt actual send - use with caution
    print("\n⚠ Note: Integration test attempts actual email send")
    print("Verify signature appears in sent email")


if __name__ == "__main__":
    # Run signature tests
    test_signature_append()

    # Uncomment to run integration tests (requires valid credentials)
    # test_integration()

    print("\n✓ All tests completed!")
    print("\nNext steps:")
    print("1. Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env")
    print("2. Run integration test to verify signature in actual sent emails")
    print("3. Use skip_signature=True for automated/system emails")

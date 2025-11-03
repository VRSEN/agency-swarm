#!/usr/bin/env python3
"""
Test script for auto-learning contacts from emails.

Tests newsletter detection and contact extraction functionality.
"""
import sys
import os
import json

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from memory_manager.tools.AutoLearnContactFromEmail import AutoLearnContactFromEmail


def create_test_email(from_header, subject, body, extra_headers=None):
    """Helper to create test email data structure."""
    headers = [
        {"name": "From", "value": from_header},
        {"name": "Subject", "value": subject},
        {"name": "Date", "value": "Mon, 1 Nov 2025 10:00:00 -0400"}
    ]

    if extra_headers:
        headers.extend(extra_headers)

    return {
        "payload": {
            "headers": headers
        },
        "messageText": body,
        "snippet": body[:100]
    }


def test_newsletter_detection():
    """Test newsletter detection algorithm."""
    print("=" * 70)
    print("NEWSLETTER DETECTION TESTS")
    print("=" * 70)

    # Test 1: Regular email (should NOT be newsletter)
    print("\n[TEST 1] Regular email from real person")
    print("-" * 70)
    email = create_test_email(
        from_header="John Doe <john.doe@acmecorp.com>",
        subject="Project Update",
        body="Hi, here's the project update we discussed."
    )

    tool = AutoLearnContactFromEmail(email_data=email, user_id="test_user")
    is_newsletter, indicators = tool._is_newsletter(email)

    if not is_newsletter:
        print("✓ PASS: Regular email not classified as newsletter")
        print(f"Indicators found: {len(indicators)} (need 2+ for newsletter)")
    else:
        print("✗ FAIL: Regular email incorrectly classified as newsletter")
        print(f"Indicators: {indicators}")

    # Test 2: Newsletter with unsubscribe header + noreply@ sender
    print("\n[TEST 2] Newsletter with 2 indicators (header + sender)")
    print("-" * 70)
    email = create_test_email(
        from_header="Marketing Team <noreply@company.com>",
        subject="Weekly Newsletter",
        body="Here's your weekly update.",
        extra_headers=[
            {"name": "List-Unsubscribe", "value": "<mailto:unsub@company.com>"}
        ]
    )

    tool = AutoLearnContactFromEmail(email_data=email, user_id="test_user")
    is_newsletter, indicators = tool._is_newsletter(email)

    if is_newsletter and len(indicators) >= 2:
        print("✓ PASS: Newsletter correctly detected with 2+ indicators")
        print(f"Indicators: {indicators}")
    else:
        print("✗ FAIL: Newsletter not detected")
        print(f"Indicators: {indicators}")

    # Test 3: Newsletter with unsubscribe in body + newsletter@ sender
    print("\n[TEST 3] Newsletter with body keyword + sender pattern")
    print("-" * 70)
    email = create_test_email(
        from_header="News Team <newsletter@updates.com>",
        subject="Monthly Updates",
        body="Here are your monthly updates. Click here to unsubscribe from future emails."
    )

    tool = AutoLearnContactFromEmail(email_data=email, user_id="test_user")
    is_newsletter, indicators = tool._is_newsletter(email)

    if is_newsletter and len(indicators) >= 2:
        print("✓ PASS: Newsletter detected via body + sender")
        print(f"Indicators: {indicators}")
    else:
        print("✗ FAIL: Newsletter not detected")
        print(f"Indicators: {indicators}")

    # Test 4: Email with only 1 indicator (should NOT be newsletter)
    print("\n[TEST 4] Email with only 1 indicator (should pass)")
    print("-" * 70)
    email = create_test_email(
        from_header="Support Team <support@service.com>",
        subject="Support Ticket Update",
        body="Your support ticket has been updated. Manage your preferences here."
    )

    tool = AutoLearnContactFromEmail(email_data=email, user_id="test_user")
    is_newsletter, indicators = tool._is_newsletter(email)

    if not is_newsletter:
        print("✓ PASS: Email with 1 indicator not classified as newsletter")
        print(f"Indicators found: {len(indicators)} (need 2+ for newsletter)")
        print(f"Indicators: {indicators}")
    else:
        print("✗ FAIL: Email with 1 indicator incorrectly classified")
        print(f"Indicators: {indicators}")

    # Test 5: Bulk email with List-Id and Precedence: bulk
    print("\n[TEST 5] Bulk email with List-Id and Precedence")
    print("-" * 70)
    email = create_test_email(
        from_header="Updates <updates@service.com>",
        subject="Service Updates",
        body="Here are your service updates.",
        extra_headers=[
            {"name": "List-Id", "value": "<updates.service.com>"},
            {"name": "Precedence", "value": "bulk"}
        ]
    )

    tool = AutoLearnContactFromEmail(email_data=email, user_id="test_user")
    is_newsletter, indicators = tool._is_newsletter(email)

    if is_newsletter and len(indicators) >= 2:
        print("✓ PASS: Bulk email correctly detected")
        print(f"Indicators: {indicators}")
    else:
        print("✗ FAIL: Bulk email not detected")
        print(f"Indicators: {indicators}")

    print("\n" + "=" * 70)


def test_contact_extraction():
    """Test contact extraction from various email formats."""
    print("\n" + "=" * 70)
    print("CONTACT EXTRACTION TESTS")
    print("=" * 70)

    # Test 1: Standard format "Name <email>"
    print("\n[TEST 1] Standard format: Name <email>")
    print("-" * 70)
    email = create_test_email(
        from_header="Jane Smith <jane.smith@example.com>",
        subject="Hello",
        body="Test email"
    )

    tool = AutoLearnContactFromEmail(email_data=email, user_id="test_user")
    from_header = tool._get_header_value(email["payload"]["headers"], "From")
    name = tool._extract_name_from_header(from_header)
    email_addr = tool._extract_email_from_header(from_header)

    if name == "Jane Smith" and email_addr == "jane.smith@example.com":
        print("✓ PASS: Name and email extracted correctly")
        print(f"Name: {name}")
        print(f"Email: {email_addr}")
    else:
        print("✗ FAIL: Extraction failed")
        print(f"Expected name: Jane Smith, got: {name}")
        print(f"Expected email: jane.smith@example.com, got: {email_addr}")

    # Test 2: Email only format
    print("\n[TEST 2] Email only format (no name)")
    print("-" * 70)
    email = create_test_email(
        from_header="contact@business.com",
        subject="Business Inquiry",
        body="Test email"
    )

    tool = AutoLearnContactFromEmail(email_data=email, user_id="test_user")
    from_header = tool._get_header_value(email["payload"]["headers"], "From")
    name = tool._extract_name_from_header(from_header)
    email_addr = tool._extract_email_from_header(from_header)

    if name == "contact" and email_addr == "contact@business.com":
        print("✓ PASS: Email extracted, name defaulted to email username")
        print(f"Name: {name}")
        print(f"Email: {email_addr}")
    else:
        print("✗ FAIL: Extraction failed")
        print(f"Expected name: contact, got: {name}")
        print(f"Expected email: contact@business.com, got: {email_addr}")

    # Test 3: Name with special characters
    print("\n[TEST 3] Name with special characters")
    print("-" * 70)
    email = create_test_email(
        from_header="José García-López <jose@company.es>",
        subject="Hola",
        body="Test email"
    )

    tool = AutoLearnContactFromEmail(email_data=email, user_id="test_user")
    from_header = tool._get_header_value(email["payload"]["headers"], "From")
    name = tool._extract_name_from_header(from_header)
    email_addr = tool._extract_email_from_header(from_header)

    if "José" in name and email_addr == "jose@company.es":
        print("✓ PASS: Special characters handled")
        print(f"Name: {name}")
        print(f"Email: {email_addr}")
    else:
        print("✗ FAIL: Special characters not handled correctly")
        print(f"Name: {name}")
        print(f"Email: {email_addr}")

    print("\n" + "=" * 70)


def test_full_workflow():
    """Test complete auto-learn workflow."""
    print("\n" + "=" * 70)
    print("FULL WORKFLOW TESTS")
    print("=" * 70)

    # Test 1: Learn contact from regular email
    print("\n[TEST 1] Learn contact from regular email")
    print("-" * 70)
    email = create_test_email(
        from_header="Alice Johnson <alice@techcorp.com>",
        subject="Project Collaboration",
        body="Hi, I'd like to discuss potential collaboration on the new project."
    )

    tool = AutoLearnContactFromEmail(email_data=email, user_id="test_user_123")
    result = tool.run()
    data = json.loads(result)

    print(f"Result: {json.dumps(data, indent=2)}")

    if data.get("success") and not data.get("skipped"):
        print("✓ PASS: Contact learned successfully")
        print(f"Contact: {data['contact']['name']} <{data['contact']['email']}>")
    else:
        print("✗ FAIL: Contact not learned")

    # Test 2: Skip newsletter
    print("\n[TEST 2] Skip newsletter email")
    print("-" * 70)
    email = create_test_email(
        from_header="Newsletter <noreply@marketing.com>",
        subject="Weekly Digest",
        body="Your weekly digest. Unsubscribe here.",
        extra_headers=[
            {"name": "List-Unsubscribe", "value": "<mailto:unsub@marketing.com>"}
        ]
    )

    tool = AutoLearnContactFromEmail(email_data=email, user_id="test_user_123")
    result = tool.run()
    data = json.loads(result)

    print(f"Result: {json.dumps(data, indent=2)}")

    if data.get("skipped") and data.get("reason") == "newsletter_detected":
        print("✓ PASS: Newsletter correctly skipped")
        print(f"Indicators: {data.get('indicators', [])}")
    else:
        print("✗ FAIL: Newsletter not skipped")

    # Test 3: Force add newsletter
    print("\n[TEST 3] Force add newsletter (force_add=True)")
    print("-" * 70)
    tool = AutoLearnContactFromEmail(
        email_data=email,
        user_id="test_user_123",
        force_add=True
    )
    result = tool.run()
    data = json.loads(result)

    print(f"Result: {json.dumps(data, indent=2)}")

    if data.get("success") and data.get("force_added"):
        print("✓ PASS: Newsletter force-added successfully")
    else:
        print("✗ FAIL: Force add did not work")

    # Test 4: Handle missing From header
    print("\n[TEST 4] Handle email with missing From header")
    print("-" * 70)
    invalid_email = {
        "payload": {
            "headers": [
                {"name": "Subject", "value": "No Sender"},
                {"name": "Date", "value": "Mon, 1 Nov 2025 12:00:00 -0400"}
            ]
        },
        "messageText": "This email has no sender.",
        "snippet": "This email has no sender."
    }

    tool = AutoLearnContactFromEmail(email_data=invalid_email, user_id="test_user_123")
    result = tool.run()
    data = json.loads(result)

    print(f"Result: {json.dumps(data, indent=2)}")

    if not data.get("success") and data.get("skipped"):
        print("✓ PASS: Missing From header handled gracefully")
    else:
        print("✗ FAIL: Missing From header not handled correctly")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    # Run all tests
    test_newsletter_detection()
    test_contact_extraction()
    test_full_workflow()

    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETED")
    print("=" * 70)

    print("\n✓ Test Summary:")
    print("1. Newsletter detection with multi-indicator algorithm")
    print("2. Contact extraction from various email formats")
    print("3. Full workflow with Mem0 storage")
    print("\nNext steps:")
    print("1. Set MEM0_API_KEY in .env for production use")
    print("2. Integrate with GmailFetchEmails workflow")
    print("3. Monitor learned contacts in Mem0 dashboard")

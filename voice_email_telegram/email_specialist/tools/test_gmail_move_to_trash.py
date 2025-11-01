#!/usr/bin/env python3
"""
Integration tests for GmailMoveToTrash tool.

This test file demonstrates various use cases for moving Gmail messages to trash.
Requires valid Composio API credentials and Gmail entity ID in .env file.
"""
import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from GmailMoveToTrash import GmailMoveToTrash
from GmailFetchEmails import GmailFetchEmails


def test_move_single_message():
    """Test moving a single message to trash."""
    print("\n" + "=" * 80)
    print("TEST 1: Move Single Message to Trash")
    print("=" * 80)

    # First fetch a message to get a real message ID
    print("\nStep 1: Fetching a message to trash...")
    fetch_tool = GmailFetchEmails(query="", max_results=1)
    fetch_result = json.loads(fetch_tool.run())

    if fetch_result.get("success") and fetch_result.get("messages"):
        message_id = fetch_result["messages"][0].get("id")
        print(f"Found message ID: {message_id}")

        print("\nStep 2: Moving message to trash...")
        tool = GmailMoveToTrash(message_id=message_id)
        result = json.loads(tool.run())

        print("\nResult:")
        print(json.dumps(result, indent=2))

        if result.get("success"):
            print("\n✅ SUCCESS: Message moved to trash")
            print(f"   - Message ID: {result['message_id']}")
            print(f"   - Recoverable: {result['recoverable']}")
            print(f"   - Recovery period: {result['recovery_period']}")
        else:
            print(f"\n❌ FAILED: {result.get('error')}")
    else:
        print("\n⚠️  No messages found to trash")
        print("Note: This is expected if inbox is empty")


def test_batch_trash_spam():
    """Test trashing multiple spam messages."""
    print("\n" + "=" * 80)
    print("TEST 2: Batch Trash Spam Messages")
    print("=" * 80)

    # Fetch spam messages
    print("\nStep 1: Fetching spam messages...")
    fetch_tool = GmailFetchEmails(query="label:SPAM", max_results=5)
    fetch_result = json.loads(fetch_tool.run())

    if fetch_result.get("success") and fetch_result.get("messages"):
        messages = fetch_result["messages"]
        print(f"Found {len(messages)} spam messages")

        print("\nStep 2: Trashing spam messages...")
        success_count = 0
        fail_count = 0

        for message in messages:
            message_id = message.get("id")
            tool = GmailMoveToTrash(message_id=message_id)
            result = json.loads(tool.run())

            if result.get("success"):
                success_count += 1
                print(f"   ✅ Trashed: {message_id}")
            else:
                fail_count += 1
                print(f"   ❌ Failed: {message_id}")

        print(f"\nResults:")
        print(f"   - Successfully trashed: {success_count}")
        print(f"   - Failed: {fail_count}")
        print(f"   - Total: {len(messages)}")
    else:
        print("\n⚠️  No spam messages found")
        print("Note: This is good! Your inbox is clean.")


def test_trash_old_emails():
    """Test trashing old emails."""
    print("\n" + "=" * 80)
    print("TEST 3: Trash Old Emails (older than 30 days)")
    print("=" * 80)

    # Fetch old emails
    print("\nStep 1: Fetching emails older than 30 days...")
    fetch_tool = GmailFetchEmails(query="older_than:30d", max_results=5)
    fetch_result = json.loads(fetch_tool.run())

    if fetch_result.get("success") and fetch_result.get("messages"):
        messages = fetch_result["messages"]
        print(f"Found {len(messages)} old messages")

        print("\nStep 2: Trashing old messages...")
        trashed_ids = []

        for message in messages:
            message_id = message.get("id")
            tool = GmailMoveToTrash(message_id=message_id)
            result = json.loads(tool.run())

            if result.get("success"):
                trashed_ids.append(message_id)
                print(f"   ✅ Trashed: {message_id}")

        print(f"\nResults:")
        print(f"   - Trashed {len(trashed_ids)} old messages")
        print(f"   - These can be recovered from Trash for 30 days")
    else:
        print("\n⚠️  No old emails found")


def test_trash_from_specific_sender():
    """Test trashing emails from specific sender."""
    print("\n" + "=" * 80)
    print("TEST 4: Trash Emails from Specific Sender")
    print("=" * 80)

    # Example: trash emails from newsletter@example.com
    sender = "newsletter@example.com"
    print(f"\nStep 1: Fetching emails from {sender}...")
    fetch_tool = GmailFetchEmails(query=f"from:{sender}", max_results=5)
    fetch_result = json.loads(fetch_tool.run())

    if fetch_result.get("success") and fetch_result.get("messages"):
        messages = fetch_result["messages"]
        print(f"Found {len(messages)} messages from {sender}")

        print(f"\nStep 2: Trashing messages from {sender}...")
        for message in messages:
            message_id = message.get("id")
            tool = GmailMoveToTrash(message_id=message_id)
            result = json.loads(tool.run())

            if result.get("success"):
                print(f"   ✅ Trashed: {message_id}")
    else:
        print(f"\n⚠️  No messages found from {sender}")


def test_validation_errors():
    """Test validation and error handling."""
    print("\n" + "=" * 80)
    print("TEST 5: Validation and Error Handling")
    print("=" * 80)

    # Test 1: Empty message_id
    print("\nTest 5.1: Empty message_id (should fail)")
    tool = GmailMoveToTrash(message_id="")
    result = json.loads(tool.run())
    print(f"Result: {result.get('error')}")
    assert result.get("success") is False, "Should fail with empty message_id"
    print("✅ Correctly rejected empty message_id")

    # Test 2: Whitespace message_id
    print("\nTest 5.2: Whitespace message_id (should fail)")
    tool = GmailMoveToTrash(message_id="   ")
    result = json.loads(tool.run())
    print(f"Result: {result.get('error')}")
    assert result.get("success") is False, "Should fail with whitespace message_id"
    print("✅ Correctly rejected whitespace message_id")

    # Test 3: Invalid message_id format
    print("\nTest 5.3: Invalid message_id (should fail)")
    tool = GmailMoveToTrash(message_id="invalid_message_id_12345")
    result = json.loads(tool.run())
    print(f"Result: {result.get('error')}")
    print("✅ Handled invalid message_id gracefully")

    print("\n✅ All validation tests passed")


def test_workflow_example():
    """Demonstrate real-world workflow: Delete emails from spam."""
    print("\n" + "=" * 80)
    print("TEST 6: Real-World Workflow Example")
    print("=" * 80)
    print("\nScenario: User says 'Delete all unread promotional emails'")
    print("=" * 80)

    # Step 1: Fetch unread promotional emails
    print("\nStep 1: Search for unread promotional emails...")
    query = "is:unread category:promotions"
    fetch_tool = GmailFetchEmails(query=query, max_results=5)
    fetch_result = json.loads(fetch_tool.run())

    if not fetch_result.get("success"):
        print(f"❌ Failed to fetch emails: {fetch_result.get('error')}")
        return

    messages = fetch_result.get("messages", [])
    print(f"✅ Found {len(messages)} unread promotional emails")

    if not messages:
        print("⚠️  No unread promotional emails found")
        return

    # Step 2: Show user what will be deleted
    print("\nStep 2: Preview emails to be deleted:")
    for i, message in enumerate(messages, 1):
        subject = message.get("subject", "No subject")
        sender = message.get("from", "Unknown sender")
        print(f"   {i}. From: {sender}")
        print(f"      Subject: {subject}")

    # Step 3: Trash the emails
    print("\nStep 3: Moving emails to trash...")
    success_count = 0
    fail_count = 0

    for message in messages:
        message_id = message.get("id")
        tool = GmailMoveToTrash(message_id=message_id)
        result = json.loads(tool.run())

        if result.get("success"):
            success_count += 1
        else:
            fail_count += 1

    # Step 4: Report results
    print("\nStep 4: Results:")
    print(f"   ✅ Successfully trashed: {success_count}")
    print(f"   ❌ Failed: {fail_count}")
    print(f"   📊 Total processed: {len(messages)}")

    if success_count > 0:
        print(f"\n💡 Note: These {success_count} emails can be recovered from")
        print("   Trash within 30 days if needed.")


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("GMAIL MOVE TO TRASH - INTEGRATION TESTS")
    print("=" * 80)
    print("\nThese tests require:")
    print("1. Valid COMPOSIO_API_KEY in .env")
    print("2. Valid GMAIL_ENTITY_ID in .env")
    print("3. Gmail account connected via Composio")
    print("\n" + "=" * 80)

    # Check credentials
    from dotenv import load_dotenv
    load_dotenv()

    if not os.getenv("COMPOSIO_API_KEY"):
        print("\n❌ ERROR: COMPOSIO_API_KEY not found in .env")
        print("Please set up your credentials first.")
        return

    if not os.getenv("GMAIL_ENTITY_ID"):
        print("\n❌ ERROR: GMAIL_ENTITY_ID not found in .env")
        print("Please set up your credentials first.")
        return

    print("✅ Credentials found, starting tests...\n")

    try:
        # Run tests
        test_validation_errors()
        test_move_single_message()
        test_batch_trash_spam()
        test_trash_old_emails()
        test_trash_from_specific_sender()
        test_workflow_example()

        print("\n" + "=" * 80)
        print("ALL TESTS COMPLETED!")
        print("=" * 80)
        print("\nKey Takeaways:")
        print("1. GmailMoveToTrash is a SOFT delete (recoverable)")
        print("2. Trashed messages can be recovered for 30 days")
        print("3. Gmail auto-deletes after 30 days")
        print("4. Use validation to prevent errors")
        print("5. Always provide user feedback on results")
        print("\n" + "=" * 80)

    except Exception as e:
        print(f"\n❌ Test suite failed with error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

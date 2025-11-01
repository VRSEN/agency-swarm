#!/usr/bin/env python3
"""
Example Usage: GmailDeleteDraft Tool

This script demonstrates practical usage patterns for the GmailDeleteDraft tool
in real-world scenarios including voice workflows, batch operations, and error handling.
"""
import json
import time
from GmailDeleteDraft import GmailDeleteDraft

# Optional: Import related tools for complete workflows
try:
    from GmailCreateDraft import GmailCreateDraft
    from GmailListDrafts import GmailListDrafts
    from GmailGetDraft import GmailGetDraft
    FULL_WORKFLOW_AVAILABLE = True
except ImportError:
    FULL_WORKFLOW_AVAILABLE = False
    print("Note: Some related tools not available. Running basic examples only.\n")


def example_1_basic_deletion():
    """Example 1: Basic draft deletion"""
    print("=" * 80)
    print("EXAMPLE 1: Basic Draft Deletion")
    print("=" * 80)

    draft_id = "r-1234567890123456789"  # Replace with actual draft ID

    print(f"\nDeleting draft: {draft_id}")
    tool = GmailDeleteDraft(draft_id=draft_id)
    result = tool.run()
    result_data = json.loads(result)

    if result_data["success"]:
        print(f"✓ Draft deleted successfully")
        print(f"  Draft ID: {result_data['draft_id']}")
        print(f"  Deleted: {result_data['deleted']}")
        print(f"  Warning: {result_data.get('warning', 'N/A')}")
    else:
        print(f"✗ Failed to delete draft")
        print(f"  Error: {result_data.get('error')}")

    return result_data


def example_2_voice_workflow():
    """Example 2: Voice-driven draft approval workflow"""
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Voice Workflow - User Rejection")
    print("=" * 80)

    # Simulate voice workflow
    print("\nScenario: User creates email via voice, then rejects it")
    print("Step 1: Draft created (simulated)")
    draft_id = "r-voice-workflow-example"

    print("Step 2: Present draft to user (simulated)")
    print("  'I've created a draft to john@example.com'")
    print("  'Subject: Meeting Tomorrow'")
    print("  'Would you like to send this?'")

    print("\nStep 3: User responds via voice")
    user_response = "No, delete it"  # Simulated voice input
    print(f"  User says: '{user_response}'")

    print("\nStep 4: Detect rejection and delete draft")
    if "delete" in user_response.lower() or "no" in user_response.lower():
        tool = GmailDeleteDraft(draft_id=draft_id)
        result = tool.run()
        result_data = json.loads(result)

        if result_data["success"]:
            print("✓ Draft deleted as requested")
            print(f"  Voice response: 'Okay, I've deleted the draft'")
        else:
            print(f"✗ Error: {result_data.get('error')}")
            print(f"  Voice response: 'Sorry, I couldn't delete the draft'")

    return result_data


def example_3_verify_before_delete():
    """Example 3: Recommended pattern - Verify before deletion"""
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Verify Before Delete (Best Practice)")
    print("=" * 80)

    draft_id = "r-verify-example"

    print(f"\nStep 1: Verify draft exists (recommended)")
    if FULL_WORKFLOW_AVAILABLE:
        verify_tool = GmailGetDraft(draft_id=draft_id)
        verify_result = verify_tool.run()
        verify_data = json.loads(verify_result)

        if verify_data.get("success"):
            print(f"✓ Draft verified:")
            print(f"  To: {verify_data.get('to', 'N/A')}")
            print(f"  Subject: {verify_data.get('subject', 'N/A')}")

            print("\nStep 2: Confirm deletion with user")
            user_confirms = True  # Simulated confirmation

            if user_confirms:
                print("Step 3: User confirmed - Delete draft")
                delete_tool = GmailDeleteDraft(draft_id=draft_id)
                delete_result = delete_tool.run()
                delete_data = json.loads(delete_result)

                if delete_data["success"]:
                    print("✓ Draft deleted successfully")
                else:
                    print(f"✗ Error: {delete_data.get('error')}")
        else:
            print(f"✗ Draft not found: {draft_id}")
    else:
        print("  (GmailGetDraft not available - skipping verification)")
        print("\nStep 2: Delete without verification (not recommended)")
        tool = GmailDeleteDraft(draft_id=draft_id)
        result = tool.run()
        print(f"  Result: {json.loads(result).get('message')}")


def example_4_batch_deletion():
    """Example 4: Batch delete multiple drafts"""
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Batch Draft Deletion")
    print("=" * 80)

    draft_ids = [
        "r-batch-draft-1",
        "r-batch-draft-2",
        "r-batch-draft-3"
    ]

    print(f"\nDeleting {len(draft_ids)} drafts...")

    results = []
    for i, draft_id in enumerate(draft_ids, 1):
        print(f"\n  [{i}/{len(draft_ids)}] Deleting: {draft_id}")
        tool = GmailDeleteDraft(draft_id=draft_id)
        result = tool.run()
        result_data = json.loads(result)
        results.append(result_data)

        if result_data["success"]:
            print(f"    ✓ Deleted")
        else:
            print(f"    ✗ Failed: {result_data.get('error')}")

        # Rate limiting: Small delay between deletions
        if i < len(draft_ids):
            time.sleep(0.2)

    # Summary
    successful = sum(1 for r in results if r["success"])
    failed = len(results) - successful

    print(f"\nBatch Deletion Summary:")
    print(f"  Total: {len(draft_ids)}")
    print(f"  ✓ Successful: {successful}")
    print(f"  ✗ Failed: {failed}")
    print(f"  Success Rate: {(successful/len(draft_ids)*100):.1f}%")

    return results


def example_5_error_handling():
    """Example 5: Comprehensive error handling"""
    print("\n" + "=" * 80)
    print("EXAMPLE 5: Error Handling Patterns")
    print("=" * 80)

    # Test case 1: Empty draft_id
    print("\nTest Case 1: Empty draft_id")
    try:
        tool = GmailDeleteDraft(draft_id="")
        result = tool.run()
        result_data = json.loads(result)
        print(f"  Response: {result_data.get('error')}")
        print(f"  ✓ Handled gracefully")
    except Exception as e:
        print(f"  ✗ Exception: {str(e)}")

    # Test case 2: Invalid draft_id format
    print("\nTest Case 2: Invalid draft_id format")
    tool = GmailDeleteDraft(draft_id="invalid-format-12345")
    result = tool.run()
    result_data = json.loads(result)
    print(f"  Success: {result_data.get('success')}")
    print(f"  Message: {result_data.get('message') or result_data.get('error')}")
    print(f"  ✓ Error handled")

    # Test case 3: Non-existent draft
    print("\nTest Case 3: Non-existent draft")
    tool = GmailDeleteDraft(draft_id="r-does-not-exist-999")
    result = tool.run()
    result_data = json.loads(result)
    print(f"  Success: {result_data.get('success')}")
    if not result_data["success"]:
        print(f"  Error: {result_data.get('error')}")
        print(f"  Possible reasons: {result_data.get('possible_reasons', [])}")
    print(f"  ✓ Error handled with suggestions")


def example_6_production_pattern():
    """Example 6: Production-ready deletion with retry logic"""
    print("\n" + "=" * 80)
    print("EXAMPLE 6: Production Pattern with Retry Logic")
    print("=" * 80)

    draft_id = "r-production-example"

    def delete_with_retry(draft_id: str, max_retries: int = 3):
        """Delete draft with automatic retry on failure"""
        for attempt in range(1, max_retries + 1):
            print(f"\n  Attempt {attempt}/{max_retries}: Deleting {draft_id}")

            tool = GmailDeleteDraft(draft_id=draft_id)
            result = tool.run()
            result_data = json.loads(result)

            if result_data["success"]:
                print(f"  ✓ Success on attempt {attempt}")
                return result_data

            print(f"  ✗ Failed: {result_data.get('error')}")

            if attempt < max_retries:
                wait_time = 2 ** attempt  # Exponential backoff
                print(f"  Waiting {wait_time}s before retry...")
                time.sleep(wait_time)

        print(f"\n  ✗ All {max_retries} attempts failed")
        return result_data

    print("\nExecuting production deletion with retry logic:")
    result = delete_with_retry(draft_id, max_retries=3)

    if result["success"]:
        print("\n✓ Production deletion successful")
    else:
        print("\n✗ Production deletion failed after retries")


def main():
    """Run all examples"""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "GmailDeleteDraft Tool - Usage Examples" + " " * 20 + "║")
    print("╚" + "=" * 78 + "╝")
    print("\nThis script demonstrates practical usage patterns for GmailDeleteDraft")
    print("Note: These examples use simulated draft IDs for demonstration")
    print("In production, use actual draft IDs from GmailListDrafts or GmailCreateDraft")

    # Run examples
    try:
        example_1_basic_deletion()
        example_2_voice_workflow()
        example_3_verify_before_delete()
        example_4_batch_deletion()
        example_5_error_handling()
        example_6_production_pattern()

        # Summary
        print("\n" + "=" * 80)
        print("ALL EXAMPLES COMPLETED")
        print("=" * 80)
        print("\n✓ 6 usage patterns demonstrated")
        print("✓ Basic deletion, voice workflow, batch operations")
        print("✓ Error handling, retry logic, production patterns")
        print("\nFor more examples, see:")
        print("  - GMAIL_DELETE_DRAFT_README.md (Complete guide)")
        print("  - GMAIL_DELETE_DRAFT_INTEGRATION.md (Integration patterns)")
        print("  - test_gmail_delete_draft.py (Test suite)")
        print("=" * 80)

    except Exception as e:
        print(f"\n✗ Error running examples: {str(e)}")
        print("Ensure COMPOSIO_API_KEY and GMAIL_ENTITY_ID are set in .env")


if __name__ == "__main__":
    main()

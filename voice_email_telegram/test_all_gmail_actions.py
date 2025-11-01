#!/usr/bin/env python3
"""
Comprehensive Gmail Composio SDK Action Testing Suite

Tests ALL Gmail actions before building tools to ensure:
1. Actions work correctly with our credentials
2. We understand the input/output format
3. We identify safe vs. risky actions
4. We have rollback strategies

Test Phases:
- Phase 1: Read-Only Actions (SAFE - no data modification)
- Phase 2: Label/Organization Actions (LOW RISK - reversible)
- Phase 3: Draft Actions (MEDIUM RISK - not sent yet)
- Phase 4: Send/Modify Actions (HIGH RISK - requires confirmation)

Author: Test Automation Specialist
Date: 2025-11-01
"""

import os
import sys
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    from composio import Composio
except ImportError:
    print("❌ ERROR: Composio SDK not installed")
    print("Install with: pip install composio-openai")
    sys.exit(1)


class GmailActionTester:
    """Comprehensive Gmail action testing framework"""

    def __init__(self):
        """Initialize the tester with credentials"""
        self.api_key = os.getenv("COMPOSIO_API_KEY")
        self.entity_id = os.getenv("GMAIL_ENTITY_ID")
        self.connection_id = os.getenv("GMAIL_CONNECTION_ID")
        self.gmail_account = os.getenv("GMAIL_ACCOUNT")

        # Validate credentials
        if not all([self.api_key, self.entity_id, self.gmail_account]):
            raise ValueError("Missing required credentials in .env file")

        # Initialize Composio client
        self.client = Composio(api_key=self.api_key)

        # Test results tracking
        self.results = {
            "phase_1_read_only": {},
            "phase_2_labels": {},
            "phase_3_drafts": {},
            "phase_4_send_modify": {}
        }

        # Test data storage (for cleanup)
        self.test_data = {
            "created_labels": [],
            "created_drafts": [],
            "sent_messages": [],
            "modified_messages": []
        }

    def print_header(self, title: str):
        """Print formatted section header"""
        print("\n" + "=" * 80)
        print(f" {title}")
        print("=" * 80)

    def print_test(self, test_name: str, status: str = "TESTING"):
        """Print test status"""
        symbols = {
            "TESTING": "🔄",
            "PASS": "✅",
            "FAIL": "❌",
            "SKIP": "⏭️",
            "WARN": "⚠️"
        }
        print(f"\n{symbols.get(status, '•')} {test_name} [{status}]")

    def execute_action(self, action_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a Composio action and return results

        Args:
            action_name: The action slug (e.g., "GMAIL_FETCH_EMAILS")
            arguments: Dictionary of action arguments

        Returns:
            Dictionary with success status and result/error
        """
        try:
            result = self.client.tools.execute(
                slug=action_name,
                arguments=arguments,
                user_id=self.entity_id
            )

            return {
                "success": True,
                "action": action_name,
                "result": result,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            return {
                "success": False,
                "action": action_name,
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": datetime.now().isoformat()
            }

    # =========================================================================
    # PHASE 1: READ-ONLY ACTIONS (SAFE - No data modification)
    # =========================================================================

    def test_gmail_fetch_emails(self) -> bool:
        """Test fetching recent emails (READ-ONLY)"""
        self.print_test("GMAIL_FETCH_EMAILS - Fetch recent emails", "TESTING")

        result = self.execute_action(
            "GMAIL_FETCH_EMAILS",
            {
                "max_results": 5,  # Only fetch 5 emails to test
                "include_spam_trash": False
            }
        )

        self.results["phase_1_read_only"]["fetch_emails"] = result

        if result["success"]:
            self.print_test("GMAIL_FETCH_EMAILS", "PASS")
            print(f"   Retrieved: {len(result.get('result', {}).get('data', {}).get('messages', []))} emails")
            return True
        else:
            self.print_test("GMAIL_FETCH_EMAILS", "FAIL")
            print(f"   Error: {result.get('error')}")
            return False

    def test_gmail_search_messages(self) -> bool:
        """Test searching emails with query (READ-ONLY)"""
        self.print_test("GMAIL_SEARCH_MESSAGES - Search emails", "TESTING")

        # Search for recent unread emails
        result = self.execute_action(
            "GMAIL_SEARCH_MESSAGES",
            {
                "query": "is:unread",
                "max_results": 5
            }
        )

        self.results["phase_1_read_only"]["search_messages"] = result

        if result["success"]:
            self.print_test("GMAIL_SEARCH_MESSAGES", "PASS")
            messages = result.get('result', {}).get('data', {}).get('messages', [])
            print(f"   Found: {len(messages)} unread emails")
            return True
        else:
            self.print_test("GMAIL_SEARCH_MESSAGES", "FAIL")
            print(f"   Error: {result.get('error')}")
            return False

    def test_gmail_get_message(self) -> bool:
        """Test getting a specific message by ID (READ-ONLY)"""
        self.print_test("GMAIL_GET_MESSAGE - Get message details", "TESTING")

        # First, get a message ID from fetch
        fetch_result = self.execute_action(
            "GMAIL_FETCH_EMAILS",
            {"max_results": 1, "include_spam_trash": False}
        )

        if not fetch_result["success"]:
            self.print_test("GMAIL_GET_MESSAGE", "SKIP")
            print("   Reason: Could not fetch emails to get message ID")
            return False

        messages = fetch_result.get('result', {}).get('data', {}).get('messages', [])
        if not messages:
            self.print_test("GMAIL_GET_MESSAGE", "SKIP")
            print("   Reason: No messages found in mailbox")
            return False

        message_id = messages[0].get('id')

        result = self.execute_action(
            "GMAIL_GET_MESSAGE",
            {"message_id": message_id}
        )

        self.results["phase_1_read_only"]["get_message"] = result

        if result["success"]:
            self.print_test("GMAIL_GET_MESSAGE", "PASS")
            msg_data = result.get('result', {}).get('data', {})
            print(f"   Message ID: {message_id}")
            print(f"   Subject: {msg_data.get('subject', 'N/A')[:50]}")
            return True
        else:
            self.print_test("GMAIL_GET_MESSAGE", "FAIL")
            print(f"   Error: {result.get('error')}")
            return False

    def test_gmail_get_thread(self) -> bool:
        """Test getting an email thread (READ-ONLY)"""
        self.print_test("GMAIL_GET_THREAD - Get email thread", "TESTING")

        # Get a thread ID from fetched emails
        fetch_result = self.execute_action(
            "GMAIL_FETCH_EMAILS",
            {"max_results": 1, "include_spam_trash": False}
        )

        if not fetch_result["success"]:
            self.print_test("GMAIL_GET_THREAD", "SKIP")
            print("   Reason: Could not fetch emails to get thread ID")
            return False

        messages = fetch_result.get('result', {}).get('data', {}).get('messages', [])
        if not messages:
            self.print_test("GMAIL_GET_THREAD", "SKIP")
            print("   Reason: No messages found")
            return False

        thread_id = messages[0].get('threadId')

        result = self.execute_action(
            "GMAIL_GET_THREAD",
            {"thread_id": thread_id}
        )

        self.results["phase_1_read_only"]["get_thread"] = result

        if result["success"]:
            self.print_test("GMAIL_GET_THREAD", "PASS")
            thread_data = result.get('result', {}).get('data', {})
            print(f"   Thread ID: {thread_id}")
            print(f"   Messages in thread: {len(thread_data.get('messages', []))}")
            return True
        else:
            self.print_test("GMAIL_GET_THREAD", "FAIL")
            print(f"   Error: {result.get('error')}")
            return False

    def test_gmail_list_labels(self) -> bool:
        """Test listing all labels (READ-ONLY)"""
        self.print_test("GMAIL_LIST_LABELS - List all labels", "TESTING")

        result = self.execute_action(
            "GMAIL_LIST_LABELS",
            {}
        )

        self.results["phase_1_read_only"]["list_labels"] = result

        if result["success"]:
            self.print_test("GMAIL_LIST_LABELS", "PASS")
            labels = result.get('result', {}).get('data', {}).get('labels', [])
            print(f"   Total labels: {len(labels)}")
            print(f"   Sample labels: {[l.get('name') for l in labels[:5]]}")
            return True
        else:
            self.print_test("GMAIL_LIST_LABELS", "FAIL")
            print(f"   Error: {result.get('error')}")
            return False

    # =========================================================================
    # PHASE 2: LABEL & ORGANIZATION ACTIONS (LOW RISK - Reversible)
    # =========================================================================

    def test_gmail_create_label(self) -> bool:
        """Test creating a label (LOW RISK - easily deletable)"""
        self.print_test("GMAIL_CREATE_LABEL - Create test label", "TESTING")

        test_label_name = f"TEST_COMPOSIO_{int(time.time())}"

        result = self.execute_action(
            "GMAIL_CREATE_LABEL",
            {"label_name": test_label_name}
        )

        self.results["phase_2_labels"]["create_label"] = result

        if result["success"]:
            label_id = result.get('result', {}).get('data', {}).get('id')
            self.test_data["created_labels"].append({
                "id": label_id,
                "name": test_label_name
            })
            self.print_test("GMAIL_CREATE_LABEL", "PASS")
            print(f"   Created label: {test_label_name}")
            print(f"   Label ID: {label_id}")
            return True
        else:
            self.print_test("GMAIL_CREATE_LABEL", "FAIL")
            print(f"   Error: {result.get('error')}")
            return False

    def test_gmail_add_label(self) -> bool:
        """Test adding a label to a message (LOW RISK - reversible)"""
        self.print_test("GMAIL_ADD_LABEL - Add label to message", "TESTING")

        # Need a label ID and message ID
        if not self.test_data["created_labels"]:
            self.print_test("GMAIL_ADD_LABEL", "SKIP")
            print("   Reason: No test labels created")
            return False

        # Get a message ID
        fetch_result = self.execute_action(
            "GMAIL_FETCH_EMAILS",
            {"max_results": 1, "include_spam_trash": False}
        )

        if not fetch_result["success"]:
            self.print_test("GMAIL_ADD_LABEL", "SKIP")
            print("   Reason: Could not fetch messages")
            return False

        messages = fetch_result.get('result', {}).get('data', {}).get('messages', [])
        if not messages:
            self.print_test("GMAIL_ADD_LABEL", "SKIP")
            print("   Reason: No messages found")
            return False

        message_id = messages[0].get('id')
        label_id = self.test_data["created_labels"][0]["id"]

        result = self.execute_action(
            "GMAIL_ADD_LABEL",
            {
                "message_id": message_id,
                "label_ids": [label_id]
            }
        )

        self.results["phase_2_labels"]["add_label"] = result

        if result["success"]:
            self.print_test("GMAIL_ADD_LABEL", "PASS")
            print(f"   Added label to message: {message_id}")
            return True
        else:
            self.print_test("GMAIL_ADD_LABEL", "FAIL")
            print(f"   Error: {result.get('error')}")
            return False

    def test_gmail_remove_label(self) -> bool:
        """Test removing a label from a message (LOW RISK - reversible)"""
        self.print_test("GMAIL_REMOVE_LABEL - Remove label from message", "TESTING")

        # This depends on add_label test
        if not self.results["phase_2_labels"].get("add_label", {}).get("success"):
            self.print_test("GMAIL_REMOVE_LABEL", "SKIP")
            print("   Reason: Add label test did not pass")
            return False

        # Use same message and label from add_label test
        fetch_result = self.execute_action(
            "GMAIL_FETCH_EMAILS",
            {"max_results": 1, "include_spam_trash": False}
        )

        if not fetch_result["success"]:
            self.print_test("GMAIL_REMOVE_LABEL", "SKIP")
            return False

        messages = fetch_result.get('result', {}).get('data', {}).get('messages', [])
        if not messages:
            self.print_test("GMAIL_REMOVE_LABEL", "SKIP")
            return False

        message_id = messages[0].get('id')
        label_id = self.test_data["created_labels"][0]["id"]

        result = self.execute_action(
            "GMAIL_REMOVE_LABEL",
            {
                "message_id": message_id,
                "label_ids": [label_id]
            }
        )

        self.results["phase_2_labels"]["remove_label"] = result

        if result["success"]:
            self.print_test("GMAIL_REMOVE_LABEL", "PASS")
            print(f"   Removed label from message: {message_id}")
            return True
        else:
            self.print_test("GMAIL_REMOVE_LABEL", "FAIL")
            print(f"   Error: {result.get('error')}")
            return False

    def test_gmail_mark_read(self) -> bool:
        """Test marking a message as read (LOW RISK - reversible)"""
        self.print_test("GMAIL_MARK_READ - Mark message as read", "TESTING")

        # Find an unread message
        search_result = self.execute_action(
            "GMAIL_SEARCH_MESSAGES",
            {"query": "is:unread", "max_results": 1}
        )

        if not search_result["success"]:
            self.print_test("GMAIL_MARK_READ", "SKIP")
            print("   Reason: Could not search for unread messages")
            return False

        messages = search_result.get('result', {}).get('data', {}).get('messages', [])
        if not messages:
            self.print_test("GMAIL_MARK_READ", "SKIP")
            print("   Reason: No unread messages found")
            return False

        message_id = messages[0].get('id')

        result = self.execute_action(
            "GMAIL_MARK_READ",
            {"message_id": message_id}
        )

        self.results["phase_2_labels"]["mark_read"] = result

        if result["success"]:
            self.print_test("GMAIL_MARK_READ", "PASS")
            print(f"   Marked as read: {message_id}")
            return True
        else:
            self.print_test("GMAIL_MARK_READ", "FAIL")
            print(f"   Error: {result.get('error')}")
            return False

    def test_gmail_mark_unread(self) -> bool:
        """Test marking a message as unread (LOW RISK - reversible)"""
        self.print_test("GMAIL_MARK_UNREAD - Mark message as unread", "TESTING")

        # Use the message we just marked as read
        if not self.results["phase_2_labels"].get("mark_read", {}).get("success"):
            self.print_test("GMAIL_MARK_UNREAD", "SKIP")
            print("   Reason: Mark read test did not pass")
            return False

        # Get a read message
        fetch_result = self.execute_action(
            "GMAIL_FETCH_EMAILS",
            {"max_results": 1, "include_spam_trash": False}
        )

        if not fetch_result["success"]:
            self.print_test("GMAIL_MARK_UNREAD", "SKIP")
            return False

        messages = fetch_result.get('result', {}).get('data', {}).get('messages', [])
        if not messages:
            self.print_test("GMAIL_MARK_UNREAD", "SKIP")
            return False

        message_id = messages[0].get('id')

        result = self.execute_action(
            "GMAIL_MARK_UNREAD",
            {"message_id": message_id}
        )

        self.results["phase_2_labels"]["mark_unread"] = result

        if result["success"]:
            self.print_test("GMAIL_MARK_UNREAD", "PASS")
            print(f"   Marked as unread: {message_id}")
            return True
        else:
            self.print_test("GMAIL_MARK_UNREAD", "FAIL")
            print(f"   Error: {result.get('error')}")
            return False

    # =========================================================================
    # PHASE 3: DRAFT ACTIONS (MEDIUM RISK - Not sent, but creates content)
    # =========================================================================

    def test_gmail_create_draft(self) -> bool:
        """Test creating an email draft (MEDIUM RISK - not sent)"""
        self.print_test("GMAIL_CREATE_DRAFT - Create email draft", "TESTING")

        result = self.execute_action(
            "GMAIL_CREATE_DRAFT",
            {
                "to": self.gmail_account,  # Send to self
                "subject": f"TEST DRAFT - Composio SDK - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "body": """This is a test draft created by the Composio SDK test suite.

This draft should NOT be sent automatically.
It exists only to test the GMAIL_CREATE_DRAFT action.

Test Details:
- Created: {datetime.now().isoformat()}
- Purpose: SDK Action Validation
- Status: DO NOT SEND

---
Voice Email Telegram Agency - Test Suite
""",
                "is_html": False
            }
        )

        self.results["phase_3_drafts"]["create_draft"] = result

        if result["success"]:
            draft_id = result.get('result', {}).get('data', {}).get('id')
            self.test_data["created_drafts"].append(draft_id)
            self.print_test("GMAIL_CREATE_DRAFT", "PASS")
            print(f"   Created draft ID: {draft_id}")
            print(f"   ⚠️  Please verify draft appears in Gmail drafts folder")
            return True
        else:
            self.print_test("GMAIL_CREATE_DRAFT", "FAIL")
            print(f"   Error: {result.get('error')}")
            return False

    def test_gmail_get_draft(self) -> bool:
        """Test retrieving a draft (READ-ONLY for drafts)"""
        self.print_test("GMAIL_GET_DRAFT - Get draft details", "TESTING")

        if not self.test_data["created_drafts"]:
            self.print_test("GMAIL_GET_DRAFT", "SKIP")
            print("   Reason: No drafts created in tests")
            return False

        draft_id = self.test_data["created_drafts"][0]

        result = self.execute_action(
            "GMAIL_GET_DRAFT",
            {"draft_id": draft_id}
        )

        self.results["phase_3_drafts"]["get_draft"] = result

        if result["success"]:
            self.print_test("GMAIL_GET_DRAFT", "PASS")
            draft_data = result.get('result', {}).get('data', {})
            print(f"   Draft ID: {draft_id}")
            print(f"   Subject: {draft_data.get('message', {}).get('subject', 'N/A')[:50]}")
            return True
        else:
            self.print_test("GMAIL_GET_DRAFT", "FAIL")
            print(f"   Error: {result.get('error')}")
            return False

    # =========================================================================
    # PHASE 4: SEND & MODIFY ACTIONS (HIGH RISK - Requires confirmation)
    # =========================================================================

    def test_gmail_send_email(self) -> bool:
        """Test sending an email (HIGH RISK - actually sends)"""
        self.print_test("GMAIL_SEND_EMAIL - Send email", "TESTING")

        print("\n⚠️  WARNING: This will send an actual email!")
        print(f"   To: {self.gmail_account} (sending to self)")
        print("   Subject: TEST EMAIL - Composio SDK Test")

        # Ask for confirmation
        response = input("\n   Proceed? (yes/NO): ").strip().lower()

        if response != "yes":
            self.print_test("GMAIL_SEND_EMAIL", "SKIP")
            print("   Reason: User declined to send test email")
            return False

        result = self.execute_action(
            "GMAIL_SEND_EMAIL",
            {
                "recipient_email": self.gmail_account,
                "subject": f"TEST EMAIL - Composio SDK - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "body": f"""This is a test email sent by the Composio SDK test suite.

Test Details:
- Sent: {datetime.now().isoformat()}
- From: {self.gmail_account}
- To: {self.gmail_account}
- Purpose: Validate GMAIL_SEND_EMAIL action

System Components:
✅ Composio SDK
✅ Gmail OAuth Integration
✅ Entity-based Authentication

If you're reading this, the send action works correctly!

---
Voice Email Telegram Agency - Test Suite
""",
                "is_html": False
            }
        )

        self.results["phase_4_send_modify"]["send_email"] = result

        if result["success"]:
            message_id = result.get('result', {}).get('data', {}).get('id')
            self.test_data["sent_messages"].append(message_id)
            self.print_test("GMAIL_SEND_EMAIL", "PASS")
            print(f"   Sent message ID: {message_id}")
            print(f"   📧 Check inbox: {self.gmail_account}")
            return True
        else:
            self.print_test("GMAIL_SEND_EMAIL", "FAIL")
            print(f"   Error: {result.get('error')}")
            return False

    def test_gmail_reply_to_email(self) -> bool:
        """Test replying to an email (HIGH RISK - sends email)"""
        self.print_test("GMAIL_REPLY_TO_EMAIL - Reply to email", "TESTING")

        # Need a message to reply to
        if not self.test_data["sent_messages"]:
            self.print_test("GMAIL_REPLY_TO_EMAIL", "SKIP")
            print("   Reason: No sent messages to reply to")
            return False

        message_id = self.test_data["sent_messages"][0]

        print("\n⚠️  WARNING: This will send a reply email!")
        response = input("   Proceed? (yes/NO): ").strip().lower()

        if response != "yes":
            self.print_test("GMAIL_REPLY_TO_EMAIL", "SKIP")
            print("   Reason: User declined to send reply")
            return False

        result = self.execute_action(
            "GMAIL_REPLY_TO_EMAIL",
            {
                "message_id": message_id,
                "body": f"""This is a test reply sent by the Composio SDK test suite.

Reply Details:
- Sent: {datetime.now().isoformat()}
- In-Reply-To: {message_id}
- Purpose: Validate GMAIL_REPLY_TO_EMAIL action

---
Voice Email Telegram Agency - Test Suite
"""
            }
        )

        self.results["phase_4_send_modify"]["reply_to_email"] = result

        if result["success"]:
            self.print_test("GMAIL_REPLY_TO_EMAIL", "PASS")
            print(f"   Sent reply to: {message_id}")
            return True
        else:
            self.print_test("GMAIL_REPLY_TO_EMAIL", "FAIL")
            print(f"   Error: {result.get('error')}")
            return False

    # =========================================================================
    # CLEANUP & UTILITIES
    # =========================================================================

    def cleanup_test_data(self):
        """Clean up test labels and drafts"""
        self.print_header("CLEANUP - Removing test data")

        # Delete test labels
        for label in self.test_data["created_labels"]:
            self.print_test(f"Deleting label: {label['name']}", "TESTING")
            try:
                result = self.execute_action(
                    "GMAIL_DELETE_LABEL",
                    {"label_id": label["id"]}
                )
                if result["success"]:
                    self.print_test(f"Deleted label: {label['name']}", "PASS")
                else:
                    self.print_test(f"Failed to delete label: {label['name']}", "WARN")
            except Exception as e:
                self.print_test(f"Error deleting label: {label['name']}", "FAIL")
                print(f"   Error: {e}")

        # Delete test drafts
        for draft_id in self.test_data["created_drafts"]:
            self.print_test(f"Deleting draft: {draft_id}", "TESTING")
            try:
                result = self.execute_action(
                    "GMAIL_DELETE_DRAFT",
                    {"draft_id": draft_id}
                )
                if result["success"]:
                    self.print_test(f"Deleted draft: {draft_id}", "PASS")
                else:
                    self.print_test(f"Failed to delete draft: {draft_id}", "WARN")
            except Exception as e:
                self.print_test(f"Error deleting draft: {draft_id}", "FAIL")
                print(f"   Error: {e}")

        print("\n⚠️  NOTE: Sent emails cannot be automatically deleted")
        print("   Please manually delete test emails from your inbox if desired")

    def generate_report(self):
        """Generate comprehensive test report"""
        self.print_header("TEST RESULTS SUMMARY")

        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        skipped_tests = 0

        for phase, tests in self.results.items():
            print(f"\n{phase.upper().replace('_', ' ')}:")
            for test_name, result in tests.items():
                total_tests += 1
                if result.get("success"):
                    passed_tests += 1
                    status = "✅ PASS"
                else:
                    if "skip" in test_name.lower() or not result:
                        skipped_tests += 1
                        status = "⏭️  SKIP"
                    else:
                        failed_tests += 1
                        status = "❌ FAIL"

                print(f"  {status} - {test_name}")
                if not result.get("success") and result.get("error"):
                    print(f"      Error: {result['error'][:100]}")

        print("\n" + "=" * 80)
        print(f"TOTAL: {total_tests} tests")
        print(f"✅ PASSED: {passed_tests}")
        print(f"❌ FAILED: {failed_tests}")
        print(f"⏭️  SKIPPED: {skipped_tests}")
        print(f"Success Rate: {(passed_tests/total_tests*100):.1f}%")
        print("=" * 80)

        # Save detailed report
        report_file = f"gmail_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump({
                "summary": {
                    "total": total_tests,
                    "passed": passed_tests,
                    "failed": failed_tests,
                    "skipped": skipped_tests,
                    "success_rate": passed_tests/total_tests*100
                },
                "results": self.results,
                "test_data": self.test_data,
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)

        print(f"\n📄 Detailed report saved to: {report_file}")

    # =========================================================================
    # MAIN TEST RUNNER
    # =========================================================================

    def run_all_tests(self, phases: List[str] = None):
        """
        Run all test phases

        Args:
            phases: List of phase numbers to run (default: all phases)
                   e.g., ["1", "2"] runs only phase 1 and 2
        """
        if phases is None:
            phases = ["1", "2", "3", "4"]

        self.print_header("GMAIL COMPOSIO SDK - COMPREHENSIVE ACTION TESTING")
        print(f"Testing Account: {self.gmail_account}")
        print(f"Entity ID: {self.entity_id}")
        print(f"Connection ID: {self.connection_id}")
        print(f"Test Phases: {', '.join(phases)}")

        # PHASE 1: READ-ONLY ACTIONS (SAFE)
        if "1" in phases:
            self.print_header("PHASE 1: READ-ONLY ACTIONS (SAFE)")
            print("These actions only read data and make no modifications\n")

            self.test_gmail_fetch_emails()
            time.sleep(1)

            self.test_gmail_search_messages()
            time.sleep(1)

            self.test_gmail_get_message()
            time.sleep(1)

            self.test_gmail_get_thread()
            time.sleep(1)

            self.test_gmail_list_labels()
            time.sleep(1)

        # PHASE 2: LABEL & ORGANIZATION (LOW RISK)
        if "2" in phases:
            self.print_header("PHASE 2: LABEL & ORGANIZATION ACTIONS (LOW RISK)")
            print("These actions modify organization but are easily reversible\n")

            self.test_gmail_create_label()
            time.sleep(1)

            self.test_gmail_add_label()
            time.sleep(1)

            self.test_gmail_remove_label()
            time.sleep(1)

            self.test_gmail_mark_read()
            time.sleep(1)

            self.test_gmail_mark_unread()
            time.sleep(1)

        # PHASE 3: DRAFT ACTIONS (MEDIUM RISK)
        if "3" in phases:
            self.print_header("PHASE 3: DRAFT ACTIONS (MEDIUM RISK)")
            print("These actions create content but do not send emails\n")

            self.test_gmail_create_draft()
            time.sleep(1)

            self.test_gmail_get_draft()
            time.sleep(1)

        # PHASE 4: SEND & MODIFY (HIGH RISK)
        if "4" in phases:
            self.print_header("PHASE 4: SEND & MODIFY ACTIONS (HIGH RISK)")
            print("⚠️  WARNING: These actions send actual emails!")
            print("You will be asked to confirm each action\n")

            self.test_gmail_send_email()
            time.sleep(1)

            self.test_gmail_reply_to_email()
            time.sleep(1)

        # Generate report
        self.generate_report()

        # Cleanup
        print("\n")
        cleanup = input("Clean up test data (labels, drafts)? (YES/no): ").strip().lower()
        if cleanup != "no":
            self.cleanup_test_data()


def main():
    """Main execution function"""
    print("=" * 80)
    print(" GMAIL COMPOSIO SDK - COMPREHENSIVE ACTION TEST SUITE")
    print("=" * 80)
    print("\nThis test suite will validate ALL Gmail actions before building tools.")
    print("\nTest Phases:")
    print("  1. READ-ONLY (safe, no modifications)")
    print("  2. LABELS & ORGANIZATION (low risk, reversible)")
    print("  3. DRAFTS (medium risk, creates content but doesn't send)")
    print("  4. SEND & MODIFY (high risk, sends actual emails)")
    print("\nYou can run specific phases or all phases.")
    print("=" * 80)

    # Ask which phases to run
    print("\nWhich phases do you want to run?")
    print("  Enter comma-separated numbers (e.g., '1,2,3') or 'all'")
    phases_input = input("Phases (default: all): ").strip().lower()

    if not phases_input or phases_input == "all":
        phases = ["1", "2", "3", "4"]
    else:
        phases = [p.strip() for p in phases_input.split(",") if p.strip() in ["1", "2", "3", "4"]]

    if not phases:
        print("❌ Invalid phase selection. Exiting.")
        return

    try:
        # Initialize tester
        tester = GmailActionTester()

        # Run tests
        tester.run_all_tests(phases=phases)

    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

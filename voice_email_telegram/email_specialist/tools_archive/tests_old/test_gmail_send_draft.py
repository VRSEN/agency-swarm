#!/usr/bin/env python3
"""
Comprehensive Test Suite for GmailSendDraft Tool
Tests all use cases, edge cases, and error handling.
"""
import json
import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from GmailCreateDraft import GmailCreateDraft
from GmailListDrafts import GmailListDrafts
from GmailSendDraft import GmailSendDraft

load_dotenv()


class GmailSendDraftTestSuite:
    """Comprehensive test suite for GmailSendDraft tool"""

    def __init__(self):
        self.test_results = []
        self.passed = 0
        self.failed = 0
        self.test_draft_ids = []

    def print_header(self, title):
        """Print formatted test header"""
        print("\n" + "=" * 80)
        print(f"{title}")
        print("=" * 80)

    def print_test(self, test_name, status="RUNNING"):
        """Print test status"""
        symbols = {
            "RUNNING": "⚙️",
            "PASS": "✅",
            "FAIL": "❌",
            "SKIP": "⏭️",
            "INFO": "ℹ️"
        }
        print(f"\n{symbols.get(status, '•')} {test_name} [{status}]")

    def record_result(self, test_name, passed, details=""):
        """Record test result"""
        self.test_results.append({
            "test": test_name,
            "passed": passed,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })
        if passed:
            self.passed += 1
        else:
            self.failed += 1

    def setup_test_drafts(self):
        """Create test drafts for sending"""
        self.print_header("SETUP: Creating Test Drafts")

        test_drafts = [
            {
                "to": "test@example.com",
                "subject": "[TEST] Simple draft for send test",
                "body": "This is a simple test draft created for GmailSendDraft testing."
            },
            {
                "to": "recipient@example.com",
                "subject": "[TEST] Draft with CC/BCC",
                "body": "Test draft with multiple recipients",
                "cc": "cc@example.com",
                "bcc": "bcc@example.com"
            },
            {
                "to": "user@example.com",
                "subject": "[TEST] HTML formatted draft",
                "body": "<html><body><h2>Test Email</h2><p>HTML content</p></body></html>"
            }
        ]

        print("\nCreating test drafts...")
        for idx, draft_config in enumerate(test_drafts, 1):
            try:
                tool = GmailCreateDraft(**draft_config)
                result = tool.run()
                result_obj = json.loads(result)

                if result_obj.get("success"):
                    draft_id = result_obj.get("draft_id")
                    self.test_draft_ids.append(draft_id)
                    print(f"  ✓ Draft {idx} created: {draft_id}")
                else:
                    print(f"  ✗ Draft {idx} failed: {result_obj.get('error')}")
            except Exception as e:
                print(f"  ✗ Draft {idx} exception: {str(e)}")

        print(f"\nCreated {len(self.test_draft_ids)} test drafts")
        return len(self.test_draft_ids) > 0

    def test_send_simple_draft(self):
        """Test 1: Send a simple draft"""
        self.print_test("Test 1: Send Simple Draft", "RUNNING")

        if not self.test_draft_ids:
            self.print_test("Test 1: Send Simple Draft", "SKIP")
            print("No test drafts available")
            return

        try:
            draft_id = self.test_draft_ids[0]
            tool = GmailSendDraft(draft_id=draft_id)
            result = tool.run()
            result_obj = json.loads(result)

            print(f"Draft ID: {draft_id}")
            print(f"Response: {json.dumps(result_obj, indent=2)}")

            if result_obj.get("success"):
                self.print_test("Test 1: Send Simple Draft", "PASS")
                self.record_result("Send Simple Draft", True, f"Message ID: {result_obj.get('message_id')}")
            else:
                self.print_test("Test 1: Send Simple Draft", "FAIL")
                self.record_result("Send Simple Draft", False, result_obj.get("error"))

        except Exception as e:
            self.print_test("Test 1: Send Simple Draft", "FAIL")
            self.record_result("Send Simple Draft", False, str(e))
            print(f"Exception: {str(e)}")

    def test_send_with_user_id(self):
        """Test 2: Send draft with explicit user_id"""
        self.print_test("Test 2: Send Draft with user_id='me'", "RUNNING")

        if len(self.test_draft_ids) < 2:
            self.print_test("Test 2: Send Draft with user_id='me'", "SKIP")
            print("Insufficient test drafts")
            return

        try:
            draft_id = self.test_draft_ids[1]
            tool = GmailSendDraft(draft_id=draft_id, user_id="me")
            result = tool.run()
            result_obj = json.loads(result)

            print(f"Draft ID: {draft_id}")
            print("User ID: me")
            print(f"Response: {json.dumps(result_obj, indent=2)}")

            if result_obj.get("success"):
                self.print_test("Test 2: Send Draft with user_id='me'", "PASS")
                self.record_result("Send with user_id", True, "user_id parameter works")
            else:
                self.print_test("Test 2: Send Draft with user_id='me'", "FAIL")
                self.record_result("Send with user_id", False, result_obj.get("error"))

        except Exception as e:
            self.print_test("Test 2: Send Draft with user_id='me'", "FAIL")
            self.record_result("Send with user_id", False, str(e))
            print(f"Exception: {str(e)}")

    def test_empty_draft_id(self):
        """Test 3: Error handling for empty draft_id"""
        self.print_test("Test 3: Empty draft_id validation", "RUNNING")

        try:
            tool = GmailSendDraft(draft_id="")
            result = tool.run()
            result_obj = json.loads(result)

            print(f"Response: {json.dumps(result_obj, indent=2)}")

            # Should fail with validation error
            if not result_obj.get("success") and "draft_id" in result_obj.get("error", "").lower():
                self.print_test("Test 3: Empty draft_id validation", "PASS")
                self.record_result("Empty draft_id validation", True, "Correctly rejected empty draft_id")
            else:
                self.print_test("Test 3: Empty draft_id validation", "FAIL")
                self.record_result("Empty draft_id validation", False, "Should reject empty draft_id")

        except Exception as e:
            # Exception is also acceptable for validation
            self.print_test("Test 3: Empty draft_id validation", "PASS")
            self.record_result("Empty draft_id validation", True, f"Raised exception: {str(e)}")
            print(f"Exception (expected): {str(e)}")

    def test_invalid_draft_id(self):
        """Test 4: Error handling for invalid draft_id"""
        self.print_test("Test 4: Invalid draft_id handling", "RUNNING")

        try:
            invalid_draft_id = "invalid_nonexistent_draft_12345"
            tool = GmailSendDraft(draft_id=invalid_draft_id)
            result = tool.run()
            result_obj = json.loads(result)

            print(f"Draft ID: {invalid_draft_id}")
            print(f"Response: {json.dumps(result_obj, indent=2)}")

            # Should fail gracefully with error message
            if not result_obj.get("success"):
                self.print_test("Test 4: Invalid draft_id handling", "PASS")
                self.record_result("Invalid draft_id handling", True, "Gracefully handled invalid ID")
            else:
                self.print_test("Test 4: Invalid draft_id handling", "FAIL")
                self.record_result("Invalid draft_id handling", False, "Should fail for invalid draft_id")

        except Exception as e:
            self.print_test("Test 4: Invalid draft_id handling", "PASS")
            self.record_result("Invalid draft_id handling", True, f"Exception handled: {str(e)}")
            print(f"Exception: {str(e)}")

    def test_missing_credentials(self):
        """Test 5: Error handling for missing credentials"""
        self.print_test("Test 5: Missing credentials validation", "RUNNING")

        # Temporarily clear credentials
        original_api_key = os.environ.get("COMPOSIO_API_KEY")
        original_entity_id = os.environ.get("GMAIL_ENTITY_ID")

        try:
            os.environ["COMPOSIO_API_KEY"] = ""
            os.environ["GMAIL_ENTITY_ID"] = ""

            tool = GmailSendDraft(draft_id="test_draft")
            result = tool.run()
            result_obj = json.loads(result)

            print(f"Response: {json.dumps(result_obj, indent=2)}")

            # Should fail with credentials error
            if not result_obj.get("success") and "credentials" in result_obj.get("error", "").lower():
                self.print_test("Test 5: Missing credentials validation", "PASS")
                self.record_result("Missing credentials validation", True, "Detected missing credentials")
            else:
                self.print_test("Test 5: Missing credentials validation", "FAIL")
                self.record_result("Missing credentials validation", False, "Should detect missing credentials")

        finally:
            # Restore credentials
            if original_api_key:
                os.environ["COMPOSIO_API_KEY"] = original_api_key
            if original_entity_id:
                os.environ["GMAIL_ENTITY_ID"] = original_entity_id

    def test_response_structure(self):
        """Test 6: Validate response structure"""
        self.print_test("Test 6: Response structure validation", "RUNNING")

        if len(self.test_draft_ids) < 3:
            self.print_test("Test 6: Response structure validation", "SKIP")
            print("Insufficient test drafts")
            return

        try:
            draft_id = self.test_draft_ids[2]
            tool = GmailSendDraft(draft_id=draft_id)
            result = tool.run()
            result_obj = json.loads(result)

            print(f"Response: {json.dumps(result_obj, indent=2)}")

            # Validate required fields
            required_fields = ["success", "message_id", "draft_id"]
            has_required = all(field in result_obj for field in required_fields)

            if has_required:
                self.print_test("Test 6: Response structure validation", "PASS")
                self.record_result("Response structure", True, "All required fields present")
            else:
                missing = [f for f in required_fields if f not in result_obj]
                self.print_test("Test 6: Response structure validation", "FAIL")
                self.record_result("Response structure", False, f"Missing fields: {missing}")

        except Exception as e:
            self.print_test("Test 6: Response structure validation", "FAIL")
            self.record_result("Response structure", False, str(e))
            print(f"Exception: {str(e)}")

    def test_voice_workflow_simulation(self):
        """Test 7: Simulate voice approval workflow"""
        self.print_test("Test 7: Voice workflow simulation", "RUNNING")
        print("\nSimulating: User says 'Send that draft'")

        # This would typically involve:
        # 1. List drafts to find the most recent
        # 2. Send the draft
        # 3. Confirm to user

        try:
            # Step 1: List drafts
            list_tool = GmailListDrafts(max_results=1)
            list_result = list_tool.run()
            list_obj = json.loads(list_result)

            if not list_obj.get("success") or not list_obj.get("drafts"):
                self.print_test("Test 7: Voice workflow simulation", "SKIP")
                print("No drafts available for voice workflow test")
                return

            # Step 2: Get the most recent draft ID
            recent_draft_id = list_obj["drafts"][0]["id"]
            print(f"Found recent draft: {recent_draft_id}")

            # Step 3: Send the draft
            send_tool = GmailSendDraft(draft_id=recent_draft_id)
            send_result = send_tool.run()
            send_obj = json.loads(send_result)

            print(f"Send response: {json.dumps(send_obj, indent=2)}")

            if send_obj.get("success"):
                self.print_test("Test 7: Voice workflow simulation", "PASS")
                self.record_result("Voice workflow", True, "Complete workflow successful")
                print(f"✓ Voice response: 'Draft sent successfully as message {send_obj.get('message_id')}'")
            else:
                self.print_test("Test 7: Voice workflow simulation", "FAIL")
                self.record_result("Voice workflow", False, send_obj.get("error"))

        except Exception as e:
            self.print_test("Test 7: Voice workflow simulation", "FAIL")
            self.record_result("Voice workflow", False, str(e))
            print(f"Exception: {str(e)}")

    def run_all_tests(self):
        """Run all tests in sequence"""
        self.print_header("GmailSendDraft Comprehensive Test Suite")
        print(f"Started: {datetime.now().isoformat()}")
        print(f"Environment: {'PRODUCTION' if os.getenv('COMPOSIO_API_KEY') else 'DEVELOPMENT'}")

        # Setup
        if not self.setup_test_drafts():
            print("\n⚠️  Warning: Could not create test drafts")
            print("Some tests will be skipped")

        # Run tests
        self.test_send_simple_draft()
        self.test_send_with_user_id()
        self.test_empty_draft_id()
        self.test_invalid_draft_id()
        self.test_missing_credentials()
        self.test_response_structure()
        self.test_voice_workflow_simulation()

        # Summary
        self.print_summary()

    def print_summary(self):
        """Print test summary"""
        self.print_header("TEST SUMMARY")

        total = self.passed + self.failed
        pass_rate = (self.passed / total * 100) if total > 0 else 0

        print(f"\nTotal Tests: {total}")
        print(f"Passed: {self.passed} ✅")
        print(f"Failed: {self.failed} ❌")
        print(f"Pass Rate: {pass_rate:.1f}%")

        print("\n" + "-" * 80)
        print("Individual Results:")
        print("-" * 80)
        for result in self.test_results:
            status = "✅ PASS" if result["passed"] else "❌ FAIL"
            print(f"{status} - {result['test']}")
            if result["details"]:
                print(f"        {result['details']}")

        print("\n" + "=" * 80)
        print("RECOMMENDATIONS")
        print("=" * 80)

        if self.failed == 0:
            print("✅ All tests passed! GmailSendDraft is production-ready.")
        else:
            print(f"⚠️  {self.failed} test(s) failed. Review errors above.")

        print("\nProduction Checklist:")
        print("  □ COMPOSIO_API_KEY configured")
        print("  □ GMAIL_ENTITY_ID configured")
        print("  □ Gmail integration connected in Composio")
        print("  □ GMAIL_SEND_DRAFT action enabled")
        print("  □ Test with real drafts before production use")

        print("\n" + "=" * 80)


if __name__ == "__main__":
    suite = GmailSendDraftTestSuite()
    suite.run_all_tests()

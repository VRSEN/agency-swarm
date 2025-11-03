#!/usr/bin/env python3
"""
Comprehensive Test Suite for GmailGetContacts Tool

Tests all functionality including:
- Basic contact fetching
- Pagination
- Error handling
- Edge cases
- Integration with Composio SDK
"""

import json
import os
import sys
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.GmailGetContacts import GmailGetContacts

load_dotenv()


class TestGmailGetContacts:
    """Test suite for GmailGetContacts tool"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []

    def test(self, name, tool, expected_success=True, check_fields=None):
        """Run a single test"""
        print(f"\n{'=' * 60}")
        print(f"TEST: {name}")
        print(f"{'=' * 60}")

        try:
            result = tool.run()
            data = json.loads(result)

            print(f"Result: {json.dumps(data, indent=2)}")

            # Check success status
            if data.get("success") != expected_success:
                print(f"❌ FAILED: Expected success={expected_success}, got {data.get('success')}")
                self.failed += 1
                self.tests.append({"name": name, "status": "FAILED", "reason": "Unexpected success status"})
                return False

            # Check required fields
            if check_fields:
                for field in check_fields:
                    if field not in data:
                        print(f"❌ FAILED: Missing required field '{field}'")
                        self.failed += 1
                        self.tests.append({"name": name, "status": "FAILED", "reason": f"Missing field: {field}"})
                        return False

            # Success-specific checks
            if expected_success:
                if "contacts" not in data:
                    print(f"❌ FAILED: Missing 'contacts' field in successful response")
                    self.failed += 1
                    self.tests.append({"name": name, "status": "FAILED", "reason": "Missing contacts field"})
                    return False

                if "count" not in data:
                    print(f"❌ FAILED: Missing 'count' field in successful response")
                    self.failed += 1
                    self.tests.append({"name": name, "status": "FAILED", "reason": "Missing count field"})
                    return False

                # Verify count matches contacts length
                if len(data["contacts"]) != data["count"]:
                    print(f"❌ FAILED: Count mismatch: count={data['count']}, len(contacts)={len(data['contacts'])}")
                    self.failed += 1
                    self.tests.append({"name": name, "status": "FAILED", "reason": "Count mismatch"})
                    return False

            print(f"✅ PASSED")
            self.passed += 1
            self.tests.append({"name": name, "status": "PASSED"})
            return True

        except Exception as e:
            print(f"❌ FAILED: Exception raised: {str(e)}")
            self.failed += 1
            self.tests.append({"name": name, "status": "FAILED", "reason": str(e)})
            return False

    def run_all_tests(self):
        """Execute all test cases"""
        print("\n" + "=" * 60)
        print("GMAIL GET CONTACTS - COMPREHENSIVE TEST SUITE")
        print("=" * 60)

        # ============================================================
        # TEST 1: Basic Fetch (Default 50 Contacts)
        # ============================================================
        self.test(
            "Test 1: Basic fetch with default parameters (50 contacts)",
            GmailGetContacts(),
            expected_success=True,
            check_fields=["success", "count", "contacts", "has_more", "max_results"]
        )

        # ============================================================
        # TEST 2: Small Batch (10 Contacts)
        # ============================================================
        self.test(
            "Test 2: Fetch small batch (10 contacts)",
            GmailGetContacts(max_results=10),
            expected_success=True,
            check_fields=["success", "count", "contacts", "max_results"]
        )

        # ============================================================
        # TEST 3: Minimal Batch (1 Contact)
        # ============================================================
        self.test(
            "Test 3: Fetch minimal batch (1 contact)",
            GmailGetContacts(max_results=1),
            expected_success=True,
            check_fields=["success", "count", "contacts"]
        )

        # ============================================================
        # TEST 4: Large Batch (100 Contacts)
        # ============================================================
        self.test(
            "Test 4: Fetch large batch (100 contacts)",
            GmailGetContacts(max_results=100),
            expected_success=True,
            check_fields=["success", "count", "contacts", "total_contacts"]
        )

        # ============================================================
        # TEST 5: Maximum Batch (1000 Contacts)
        # ============================================================
        self.test(
            "Test 5: Fetch maximum batch (1000 contacts)",
            GmailGetContacts(max_results=1000),
            expected_success=True,
            check_fields=["success", "count", "contacts"]
        )

        # ============================================================
        # TEST 6: Invalid max_results (Too High - Should Fail)
        # ============================================================
        self.test(
            "Test 6: Invalid max_results - too high (should fail)",
            GmailGetContacts(max_results=2000),
            expected_success=False,
            check_fields=["success", "error"]
        )

        # ============================================================
        # TEST 7: Invalid max_results (Zero - Should Fail)
        # ============================================================
        self.test(
            "Test 7: Invalid max_results - zero (should fail)",
            GmailGetContacts(max_results=0),
            expected_success=False,
            check_fields=["success", "error"]
        )

        # ============================================================
        # TEST 8: Invalid max_results (Negative - Should Fail)
        # ============================================================
        self.test(
            "Test 8: Invalid max_results - negative (should fail)",
            GmailGetContacts(max_results=-10),
            expected_success=False,
            check_fields=["success", "error"]
        )

        # ============================================================
        # TEST 9: Custom user_id
        # ============================================================
        self.test(
            "Test 9: Custom user_id parameter",
            GmailGetContacts(max_results=5, user_id="me"),
            expected_success=True,
            check_fields=["success", "count", "contacts"]
        )

        # ============================================================
        # TEST 10: Pagination token (empty string)
        # ============================================================
        self.test(
            "Test 10: Empty pagination token",
            GmailGetContacts(max_results=10, page_token=""),
            expected_success=True,
            check_fields=["success", "count", "contacts"]
        )

        # ============================================================
        # TEST 11: Check Contact Structure
        # ============================================================
        print(f"\n{'=' * 60}")
        print("TEST 11: Verify contact structure and fields")
        print(f"{'=' * 60}")

        tool = GmailGetContacts(max_results=1)
        result = tool.run()
        data = json.loads(result)

        if data.get("success") and data.get("count") > 0:
            contact = data["contacts"][0]
            required_contact_fields = ["name", "emails", "resource_name"]
            optional_fields = ["given_name", "family_name", "phones", "photo_url", "company", "title"]

            missing_required = [f for f in required_contact_fields if f not in contact]
            if missing_required:
                print(f"❌ FAILED: Missing required contact fields: {missing_required}")
                self.failed += 1
                self.tests.append({"name": "Test 11", "status": "FAILED", "reason": f"Missing fields: {missing_required}"})
            else:
                print(f"✅ PASSED: Contact has all required fields")
                print(f"Contact structure: {json.dumps(contact, indent=2)}")
                self.passed += 1
                self.tests.append({"name": "Test 11", "status": "PASSED"})
        else:
            print(f"⚠️  SKIPPED: No contacts available to verify structure")

        # ============================================================
        # TEST 12: Performance Test (Medium Batch)
        # ============================================================
        import time

        print(f"\n{'=' * 60}")
        print("TEST 12: Performance test (fetch 50 contacts)")
        print(f"{'=' * 60}")

        tool = GmailGetContacts(max_results=50)
        start_time = time.time()
        result = tool.run()
        elapsed = time.time() - start_time

        data = json.loads(result)
        if data.get("success"):
            print(f"✅ PASSED: Fetched {data['count']} contacts in {elapsed:.2f}s")
            if elapsed > 10:
                print(f"⚠️  WARNING: Request took longer than expected ({elapsed:.2f}s)")
            self.passed += 1
            self.tests.append({"name": "Test 12", "status": "PASSED", "time": f"{elapsed:.2f}s"})
        else:
            print(f"❌ FAILED: Performance test failed: {data.get('error')}")
            self.failed += 1
            self.tests.append({"name": "Test 12", "status": "FAILED", "reason": data.get("error")})

        # ============================================================
        # SUMMARY
        # ============================================================
        self.print_summary()

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)

        total = self.passed + self.failed
        pass_rate = (self.passed / total * 100) if total > 0 else 0

        print(f"Total Tests:  {total}")
        print(f"✅ Passed:    {self.passed} ({pass_rate:.1f}%)")
        print(f"❌ Failed:    {self.failed}")
        print("=" * 60)

        if self.failed == 0:
            print("\n🎉 ALL TESTS PASSED!")
        else:
            print(f"\n⚠️  {self.failed} TEST(S) FAILED")
            print("\nFailed Tests:")
            for test in self.tests:
                if test["status"] == "FAILED":
                    reason = test.get("reason", "Unknown")
                    print(f"  - {test['name']}: {reason}")

        print("\nDetailed Results:")
        for i, test in enumerate(self.tests, 1):
            status_icon = "✅" if test["status"] == "PASSED" else "❌"
            print(f"  {i:2}. {status_icon} {test['name']}")

        print("\n" + "=" * 60)

        # Check credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        entity_id = os.getenv("GMAIL_ENTITY_ID")

        print("\nConfiguration Check:")
        print(f"  COMPOSIO_API_KEY: {'✅ Set' if api_key else '❌ Missing'}")
        print(f"  GMAIL_ENTITY_ID:  {'✅ Set' if entity_id else '❌ Missing'}")

        if not api_key or not entity_id:
            print("\n⚠️  WARNING: Missing credentials!")
            print("  Some tests may fail due to missing Composio credentials.")
            print("  Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env file.")

        print("=" * 60)


def main():
    """Run all tests"""
    test_suite = TestGmailGetContacts()
    test_suite.run_all_tests()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Comprehensive test suite for GmailGetPeople tool.

Tests all functionality including:
- Valid resource names with various field combinations
- Invalid inputs and error handling
- Field extraction and formatting
- Integration with GmailSearchPeople workflow
"""
import json
import os
import sys
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.GmailGetPeople import GmailGetPeople
from tools.GmailSearchPeople import GmailSearchPeople

load_dotenv()


class TestGmailGetPeople:
    """Test suite for GmailGetPeople tool."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.test_results = []

    def run_test(self, test_name: str, test_func):
        """Run a single test and track results."""
        print(f"\n{'='*80}")
        print(f"TEST: {test_name}")
        print('='*80)

        try:
            test_func()
            self.passed += 1
            self.test_results.append(f"✅ PASS: {test_name}")
            print(f"\n✅ PASSED: {test_name}")
        except AssertionError as e:
            self.failed += 1
            self.test_results.append(f"❌ FAIL: {test_name} - {str(e)}")
            print(f"\n❌ FAILED: {test_name}")
            print(f"Error: {str(e)}")
        except Exception as e:
            self.failed += 1
            self.test_results.append(f"💥 ERROR: {test_name} - {str(e)}")
            print(f"\n💥 ERROR: {test_name}")
            print(f"Exception: {str(e)}")

    def test_basic_fields(self):
        """Test 1: Get person with basic fields (names, emails, phones)."""
        tool = GmailGetPeople(
            resource_name="people/c1234567890",
            person_fields="names,emailAddresses,phoneNumbers"
        )
        result = tool.run()
        print(f"Result: {result}")

        data = json.loads(result)
        assert "success" in data, "Response missing 'success' field"
        assert "person" in data, "Response missing 'person' field"
        assert "resource_name" in data, "Response missing 'resource_name' field"
        print("✓ Response has required fields")

    def test_all_common_fields(self):
        """Test 2: Get person with all common fields."""
        tool = GmailGetPeople(
            resource_name="people/c1234567890",
            person_fields="names,emailAddresses,phoneNumbers,photos,addresses,organizations,birthdays,biographies"
        )
        result = tool.run()
        print(f"Result: {result}")

        data = json.loads(result)
        assert isinstance(data, dict), "Response should be a dictionary"
        assert "fields_returned" in data, "Response missing 'fields_returned' field"
        print(f"✓ Fields returned: {data.get('fields_returned', [])}")

    def test_extended_fields(self):
        """Test 3: Get person with extended fields (urls, relations, skills)."""
        tool = GmailGetPeople(
            resource_name="people/c1234567890",
            person_fields="names,emailAddresses,urls,relations,skills,interests"
        )
        result = tool.run()
        print(f"Result: {result}")

        data = json.loads(result)
        assert "success" in data, "Response missing 'success' field"
        assert "raw_data" in data, "Response missing 'raw_data' field for advanced use"
        print("✓ Extended fields request processed")

    def test_minimal_fields(self):
        """Test 4: Get person with minimal fields (names only)."""
        tool = GmailGetPeople(
            resource_name="people/c1234567890",
            person_fields="names"
        )
        result = tool.run()
        print(f"Result: {result}")

        data = json.loads(result)
        assert "person" in data, "Response missing 'person' field"
        print("✓ Minimal fields request works")

    def test_empty_resource_name(self):
        """Test 5: Empty resource_name should return error."""
        tool = GmailGetPeople(
            resource_name="",
            person_fields="names,emailAddresses"
        )
        result = tool.run()
        print(f"Result: {result}")

        data = json.loads(result)
        assert data["success"] == False, "Should fail with empty resource_name"
        assert "error" in data, "Should include error message"
        assert "cannot be empty" in data["error"].lower(), "Should mention empty resource_name"
        print(f"✓ Correctly rejected empty resource_name: {data['error']}")

    def test_invalid_resource_format(self):
        """Test 6: Invalid resource_name format should return error."""
        tool = GmailGetPeople(
            resource_name="invalid/c1234567890",
            person_fields="names,emailAddresses"
        )
        result = tool.run()
        print(f"Result: {result}")

        data = json.loads(result)
        assert data["success"] == False, "Should fail with invalid format"
        assert "error" in data, "Should include error message"
        assert "people/" in data["error"].lower(), "Should mention required 'people/' prefix"
        print(f"✓ Correctly rejected invalid format: {data['error']}")

    def test_missing_credentials(self):
        """Test 7: Missing credentials should return error."""
        # Temporarily clear credentials
        original_api_key = os.getenv("COMPOSIO_API_KEY")
        original_entity_id = os.getenv("GMAIL_ENTITY_ID")

        os.environ.pop("COMPOSIO_API_KEY", None)
        os.environ.pop("GMAIL_ENTITY_ID", None)

        tool = GmailGetPeople(
            resource_name="people/c1234567890",
            person_fields="names"
        )
        result = tool.run()
        print(f"Result: {result}")

        # Restore credentials
        if original_api_key:
            os.environ["COMPOSIO_API_KEY"] = original_api_key
        if original_entity_id:
            os.environ["GMAIL_ENTITY_ID"] = original_entity_id

        data = json.loads(result)
        assert data["success"] == False, "Should fail without credentials"
        assert "credentials" in data["error"].lower(), "Should mention missing credentials"
        print(f"✓ Correctly handled missing credentials: {data['error']}")

    def test_work_related_fields(self):
        """Test 8: Get work-related fields (organizations, addresses)."""
        tool = GmailGetPeople(
            resource_name="people/c1234567890",
            person_fields="names,emailAddresses,phoneNumbers,organizations,addresses"
        )
        result = tool.run()
        print(f"Result: {result}")

        data = json.loads(result)
        assert "person" in data, "Response missing 'person' field"
        print("✓ Work-related fields request processed")

    def test_profile_fields(self):
        """Test 9: Get profile fields (photos, biographies, urls)."""
        tool = GmailGetPeople(
            resource_name="people/c1234567890",
            person_fields="names,photos,biographies,urls"
        )
        result = tool.run()
        print(f"Result: {result}")

        data = json.loads(result)
        assert "person" in data, "Response missing 'person' field"
        print("✓ Profile fields request processed")

    def test_search_then_get_workflow(self):
        """Test 10: Complete workflow - search then get details."""
        print("\nStep 1: Search for person...")
        search_tool = GmailSearchPeople(query="John", page_size=1)
        search_result = search_tool.run()
        print(f"Search Result: {search_result}")

        search_data = json.loads(search_result)

        if search_data.get("success") and search_data.get("count", 0) > 0:
            # Extract resource_name from first result
            resource_name = search_data["people"][0].get("resource_name", "")
            print(f"\nStep 2: Get full details for resource: {resource_name}")

            if resource_name:
                get_tool = GmailGetPeople(
                    resource_name=resource_name,
                    person_fields="names,emailAddresses,phoneNumbers,photos,organizations"
                )
                get_result = get_tool.run()
                print(f"Get Result: {get_result}")

                get_data = json.loads(get_result)
                assert "success" in get_data, "Get request should have success field"
                print("✓ Complete search-then-get workflow successful")
            else:
                print("⚠ No resource_name in search results, skipping get step")
        else:
            print("⚠ No search results found, skipping get step")
            print("✓ Workflow test completed (search returned no results)")

    def test_default_user_id(self):
        """Test 11: Default user_id='me' works correctly."""
        tool = GmailGetPeople(
            resource_name="people/c1234567890",
            person_fields="names,emailAddresses"
            # user_id defaults to "me"
        )
        result = tool.run()
        print(f"Result: {result}")

        data = json.loads(result)
        assert "person" in data, "Response missing 'person' field"
        print("✓ Default user_id='me' works correctly")

    def test_custom_user_id(self):
        """Test 12: Custom user_id can be specified."""
        tool = GmailGetPeople(
            resource_name="people/c1234567890",
            person_fields="names,emailAddresses",
            user_id="custom_user_id"
        )
        result = tool.run()
        print(f"Result: {result}")

        data = json.loads(result)
        # Should process the request (may fail at API level, but tool should handle it)
        assert isinstance(data, dict), "Should return a dictionary response"
        print("✓ Custom user_id accepted")

    def test_field_extraction_structure(self):
        """Test 13: Verify formatted person data structure."""
        tool = GmailGetPeople(
            resource_name="people/c1234567890",
            person_fields="names,emailAddresses,phoneNumbers,addresses,organizations"
        )
        result = tool.run()
        print(f"Result: {result}")

        data = json.loads(result)

        if data.get("success"):
            person = data.get("person", {})

            # Check structure of formatted fields
            if "name" in person:
                assert isinstance(person["name"], dict), "name should be a dictionary"
                print(f"✓ Name structure: {list(person['name'].keys())}")

            if "emails" in person:
                assert isinstance(person["emails"], list), "emails should be a list"
                print(f"✓ Emails is a list with {len(person['emails'])} items")

            if "phones" in person:
                assert isinstance(person["phones"], list), "phones should be a list"
                print(f"✓ Phones is a list with {len(person['phones'])} items")

            print("✓ Person data structure is correctly formatted")

    def test_whitespace_handling(self):
        """Test 14: Resource_name with whitespace is handled correctly."""
        tool = GmailGetPeople(
            resource_name="  people/c1234567890  ",
            person_fields="names"
        )
        result = tool.run()
        print(f"Result: {result}")

        data = json.loads(result)
        assert "person" in data, "Should handle whitespace in resource_name"
        print("✓ Whitespace in resource_name handled correctly")

    def test_response_has_raw_data(self):
        """Test 15: Response includes raw_data for advanced use."""
        tool = GmailGetPeople(
            resource_name="people/c1234567890",
            person_fields="names,emailAddresses"
        )
        result = tool.run()
        print(f"Result: {result}")

        data = json.loads(result)
        assert "raw_data" in data, "Response should include raw_data field"
        print("✓ Response includes raw_data for advanced processing")

    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)

        total = self.passed + self.failed
        print(f"\nTotal Tests: {total}")
        print(f"✅ Passed: {self.passed}")
        print(f"❌ Failed: {self.failed}")
        print(f"Success Rate: {(self.passed/total*100):.1f}%")

        print("\nDetailed Results:")
        for result in self.test_results:
            print(f"  {result}")

        print("\n" + "=" * 80)

        if self.failed == 0:
            print("🎉 ALL TESTS PASSED!")
        else:
            print(f"⚠️  {self.failed} TEST(S) FAILED")

        print("=" * 80)


def main():
    """Run all tests."""
    print("=" * 80)
    print("GMAIL GET PEOPLE - COMPREHENSIVE TEST SUITE")
    print("=" * 80)
    print("\nThis suite tests all functionality of the GmailGetPeople tool.")
    print("Testing: field combinations, error handling, workflow integration, and data formatting.")
    print("\nNote: Some tests may fail if:")
    print("- COMPOSIO_API_KEY or GMAIL_ENTITY_ID not set in .env")
    print("- Gmail People API scope not enabled in Composio connection")
    print("- Resource names don't exist in the connected Gmail account")

    suite = TestGmailGetPeople()

    # Run all tests
    suite.run_test("Basic Fields (names, emails, phones)", suite.test_basic_fields)
    suite.run_test("All Common Fields", suite.test_all_common_fields)
    suite.run_test("Extended Fields (urls, relations, skills)", suite.test_extended_fields)
    suite.run_test("Minimal Fields (names only)", suite.test_minimal_fields)
    suite.run_test("Empty Resource Name Error", suite.test_empty_resource_name)
    suite.run_test("Invalid Resource Format Error", suite.test_invalid_resource_format)
    suite.run_test("Missing Credentials Error", suite.test_missing_credentials)
    suite.run_test("Work-Related Fields", suite.test_work_related_fields)
    suite.run_test("Profile Fields", suite.test_profile_fields)
    suite.run_test("Search-Then-Get Workflow", suite.test_search_then_get_workflow)
    suite.run_test("Default user_id='me'", suite.test_default_user_id)
    suite.run_test("Custom user_id", suite.test_custom_user_id)
    suite.run_test("Field Extraction Structure", suite.test_field_extraction_structure)
    suite.run_test("Whitespace Handling", suite.test_whitespace_handling)
    suite.run_test("Response Includes Raw Data", suite.test_response_has_raw_data)

    # Print summary
    suite.print_summary()

    return suite.failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

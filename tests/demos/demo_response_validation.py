#!/usr/bin/env python3
"""
Improved demonstration of response validation functionality.

This comprehensive demo shows:
1. Validation feedback loop (agent learns from errors)
2. Different validation types (content, format, policy)
3. Exception handling when retries are exhausted
4. Conversation history analysis
"""

import json

from agency_swarm import Agency, Agent


class ValidationTestResults:
    """Track test results for reporting."""

    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.details = []

    def add_result(self, test_name: str, passed: bool, details: str = ""):
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
        self.details.append({"test": test_name, "passed": passed, "details": details})

    def print_summary(self):
        print(f"\n{'='*60}")
        print(f"VALIDATION TEST SUMMARY: {self.tests_passed}/{self.tests_run} PASSED")
        print(f"{'='*60}")

        for result in self.details:
            status = "✅ PASS" if result["passed"] else "❌ FAIL"
            print(f"{status}: {result['test']}")
            if result["details"]:
                print(f"    {result['details']}")

        if self.tests_passed == self.tests_run:
            print("\n🎉 ALL VALIDATION TESTS PASSED!")
            print("✅ Validation system is working correctly")
        else:
            print(f"\n⚠️  {self.tests_run - self.tests_passed} TESTS FAILED")
            print("❌ Validation system has issues that need attention")


def test_simple_keyword_validation(results: ValidationTestResults):
    """Test basic keyword validation with learning."""
    print("\n🧪 Test 1: Simple Keyword Validation")

    def keyword_validator(message: str) -> str:
        if "VALIDATED" not in message:
            raise ValueError("Your response must contain the word VALIDATED")
        return message

    agent = Agent(
        name="KeywordAgent",
        description="Agent that learns keyword requirements",
        instructions="Respond helpfully. If you receive an error message, follow its instructions exactly.",
        validation_attempts=2,
    )
    agent.response_validator = keyword_validator

    try:
        agency = Agency([agent])
        response = agency.get_completion("Say hello briefly.")

        if "VALIDATED" in response:
            results.add_result(
                "Simple Keyword Validation", True, f"Agent learned and included keyword: {response[:50]}..."
            )

            # Show conversation history
            print("📝 Conversation shows feedback loop:")
            messages = agency.main_thread.get_messages()
            for i, msg in enumerate(reversed(messages[-4:])):  # Show last 4 messages
                role_icon = "🤖" if msg.role == "assistant" else "👤"
                try:
                    content = (
                        msg.content[0].text.value[:60] + "..."
                        if len(msg.content[0].text.value) > 60
                        else msg.content[0].text.value
                    )
                except (AttributeError, IndexError):
                    content = str(msg.content)[:60] + "..."
                print(f"  {i+1}. {role_icon} {content}")
        else:
            results.add_result("Simple Keyword Validation", False, f"Agent failed to learn: {response[:50]}...")
    except Exception as e:
        results.add_result("Simple Keyword Validation", False, f"Unexpected exception: {str(e)[:100]}...")


def test_json_format_validation(results: ValidationTestResults):
    """Test JSON format validation."""
    print("\n🧪 Test 2: JSON Format Validation")

    def json_validator(message: str) -> str:
        try:
            data = json.loads(message)
            if not isinstance(data, dict):
                raise ValueError("Response must be a JSON object")
            if "status" not in data:
                raise ValueError("Response must include a 'status' field")
            return message
        except json.JSONDecodeError:
            raise ValueError("Response must be valid JSON format. Example: {'status': 'success', 'message': 'Hello!'}")

    agent = Agent(
        name="JSONAgent",
        description="Agent that returns structured JSON responses",
        instructions="Always respond in JSON format. If you receive format errors, correct the JSON structure.",
        validation_attempts=3,
    )
    agent.response_validator = json_validator

    try:
        agency = Agency([agent])
        response = agency.get_completion("Provide a greeting message.")

        # If we get a response, verify it's valid JSON with required fields
        try:
            data = json.loads(response)
            if isinstance(data, dict) and "status" in data:
                results.add_result("JSON Format Validation", True, f"Agent learned JSON format: {response[:50]}...")
            else:
                # Agent produced response but validation system failed to catch invalid structure
                results.add_result(
                    "JSON Format Validation", False, f"Validation missed invalid JSON structure: {response[:50]}..."
                )
        except json.JSONDecodeError:
            # Agent produced response but validation system failed to catch invalid JSON
            results.add_result("JSON Format Validation", False, f"Validation missed invalid JSON: {response[:50]}...")

    except ValueError as e:
        # This is expected and correct - validation system working properly by raising exception
        if "JSON" in str(e).upper():
            results.add_result(
                "JSON Format Validation", True, f"Validation correctly rejected invalid JSON: {str(e)[:60]}..."
            )
        else:
            results.add_result("JSON Format Validation", False, f"Unexpected validation error: {str(e)[:60]}...")
    except Exception as e:
        # Unexpected system error
        results.add_result("JSON Format Validation", False, f"System error during JSON validation: {str(e)[:100]}...")


def test_validation_exception_raising(results: ValidationTestResults):
    """Test that exceptions are raised when validation fails immediately (no retries allowed)."""
    print("\n🧪 Test 3: Exception Raising (No Retries)")

    def strict_validator(message: str) -> str:
        # Require a very specific format that's unlikely to be used naturally
        if not message.startswith("SYSTEM_VALIDATED_RESPONSE:"):
            raise ValueError("Response must start with 'SYSTEM_VALIDATED_RESPONSE:'")
        return message

    agent = Agent(
        name="StrictAgent",
        description="Agent with very strict validation",
        instructions="Always respond with simple, natural language. Do not use special prefixes or formatting.",
        validation_attempts=0,  # No retries allowed - should raise exception immediately
    )
    agent.response_validator = strict_validator

    try:
        agency = Agency([agent])
        response = agency.get_completion("Say hello.")

        # If we get here, the validation didn't raise an exception (unexpected)
        results.add_result("Exception Raising", False, f"Expected exception but got response: {response[:50]}...")
    except ValueError as e:
        # This is expected - validation should raise exception immediately
        if "SYSTEM_VALIDATED_RESPONSE" in str(e):
            results.add_result("Exception Raising", True, f"Exception correctly raised: {str(e)[:60]}...")
        else:
            results.add_result("Exception Raising", False, f"Wrong exception content: {str(e)[:60]}...")
    except Exception as e:
        results.add_result(
            "Exception Raising", False, f"Unexpected exception type: {type(e).__name__}: {str(e)[:50]}..."
        )


def test_multiple_retry_attempts(results: ValidationTestResults):
    """Test multiple validation retry attempts with realistic validation."""
    print("\n🧪 Test 4: Multiple Retry Attempts")

    def format_validator(message: str) -> str:
        """Require 'GREETING:' prefix."""
        if not message.upper().startswith("GREETING:"):
            raise ValueError("Response must start with 'GREETING:' followed by your message")
        return message

    agent = Agent(
        name="FormatAgent",
        description="Agent that learns specific formatting",
        instructions="Respond naturally. If you receive formatting instructions, follow them exactly.",
        validation_attempts=3,  # Allow multiple retries
    )
    agent.response_validator = format_validator

    try:
        agency = Agency([agent])
        response = agency.get_completion("Please greet the user.")

        if response.upper().startswith("GREETING:"):
            results.add_result("Multiple Retry Attempts", True, f"Agent learned format: {response[:50]}...")

            # Count validation messages in conversation
            messages = agency.main_thread.get_messages()
            validation_messages = []
            for msg in messages:
                try:
                    if msg.role == "user" and "GREETING:" in msg.content[0].text.value:
                        validation_messages.append(msg)
                except (AttributeError, IndexError):
                    # Handle different message structures
                    if msg.role == "user" and "GREETING:" in str(msg.content):
                        validation_messages.append(msg)

            print(f"📊 Found {len(validation_messages)} validation retry messages")
        else:
            results.add_result("Multiple Retry Attempts", False, f"Agent failed to learn format: {response[:50]}...")
    except Exception as e:
        results.add_result("Multiple Retry Attempts", False, f"Exception during retry test: {str(e)[:100]}...")


def main():
    """Run comprehensive validation tests."""
    print("🔧 Comprehensive Response Validation Test Suite")
    print("=" * 60)
    print("Testing validation feedback loops, error handling, and edge cases...")

    results = ValidationTestResults()

    # Run all tests
    test_simple_keyword_validation(results)
    test_json_format_validation(results)
    test_validation_exception_raising(results)
    test_multiple_retry_attempts(results)

    # Print final summary
    results.print_summary()

    return results.tests_passed == results.tests_run


if __name__ == "__main__":
    success = main()

    if success:
        print("\n🚀 VALIDATION SYSTEM FULLY FUNCTIONAL!")
        print("✅ All validation scenarios work correctly")
        print("✅ Agents learn from validation errors when possible")
        print("✅ Exceptions are raised when retries are exhausted")
        print("✅ Multiple validation types supported")
    else:
        print("\n⚠️  VALIDATION SYSTEM HAS ISSUES")
        print("❌ Some validation scenarios failed")
        print("🔍 Check the test details above for specific problems")

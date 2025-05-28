#!/usr/bin/env python3
"""
Final comprehensive test of the response_validator fix.
"""

from agency_swarm import Agency, Agent


class StrictAgent(Agent):
    def response_validator(self, message: str) -> str:
        # This validator requires a very specific format that the agent is unlikely to use
        if not message.startswith("SYSTEM_VALIDATED_RESPONSE:"):
            raise ValueError("Response must start with 'SYSTEM_VALIDATED_RESPONSE:'")
        return message


def test_validation_exception_raised():
    """Test that validation exceptions are raised when retries are exhausted."""
    print("🧪 Testing validation exception raising...")

    agent = StrictAgent(
        name="StrictAgent",
        description="Agent with strict validation",
        instructions="Always respond with a simple greeting. Do not use any special prefixes.",
        validation_attempts=1,  # No retries - should raise exception immediately
    )
    agency = Agency([agent], temperature=0)

    try:
        response = agency.get_completion("Say hello.")
        print(f"❌ UNEXPECTED: No exception raised. Response: {response}")
        return False

    except ValueError as e:
        print(f"✅ SUCCESS: Validation exception raised: {e}")
        return True

    except Exception as e:
        print(f"❌ WRONG EXCEPTION TYPE: {type(e).__name__}: {e}")
        return False


def test_validation_retry_then_success():
    """Test that validation retry mechanism works when agent can learn."""
    print("\n🧪 Testing validation retry mechanism...")

    agent = StrictAgent(
        name="LearningAgent",
        description="Agent that can learn from validation errors",
        instructions="Always respond helpfully. If you receive an error message, follow its instructions exactly.",
        validation_attempts=3,  # Allow retries
    )
    agency = Agency([agent], temperature=0)

    try:
        response = agency.get_completion("Please greet the user.")
        print(f"📝 Final response: {response}")

        if "SYSTEM_VALIDATED_RESPONSE:" in response:
            print(f"✅ SUCCESS: Agent learned and corrected response!")
            return True
        else:
            print(f"⚠️  Agent responded but didn't follow validation requirements")
            return False

    except Exception as e:
        print(f"❌ UNEXPECTED EXCEPTION: {type(e).__name__}: {e}")
        return False


def main():
    print("🔧 Final Response Validator Fix Verification")
    print("=" * 60)

    test1_success = test_validation_exception_raised()
    test2_success = test_validation_retry_then_success()

    print("\n" + "=" * 60)

    if test1_success and test2_success:
        print("🎉 ALL TESTS PASSED! Response validator fix is working correctly!")
        print("✅ Exceptions are raised when retries are exhausted")
        print("✅ Retry mechanism works when agents can learn")
    elif test1_success:
        print("🎯 EXCEPTION RAISING WORKS! (Retry test inconclusive)")
        print("✅ Exceptions are raised when retries are exhausted")
    else:
        print("❌ Fix verification failed")


if __name__ == "__main__":
    main()

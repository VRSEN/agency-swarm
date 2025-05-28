#!/usr/bin/env python3
"""
Comprehensive demo showing that the response_validator bugs are fixed.
"""

from agency_swarm import Agency, Agent


class StrictValidationAgent(Agent):
    def response_validator(self, message: str) -> str:
        if "VALIDATED" not in message:
            raise ValueError("Response must contain the word 'VALIDATED'.")
        return message


def test_exception_raising():
    """Test that validation exceptions are raised when retries are exhausted."""
    print("🧪 Testing exception raising when retries exhausted...")

    agent = StrictValidationAgent(
        name="StubbornAgent",
        description="Agent that doesn't learn",
        instructions="Always respond 'Hello!' regardless of error messages.",
        validation_attempts=1,  # No retries
    )
    agency = Agency([agent], temperature=0)

    try:
        response = agency.get_completion("Say hello.")
        print(f"❌ UNEXPECTED: No exception raised. Response: {response}")
        return False

    except ValueError as e:
        print(f"✅ SUCCESS: Exception properly raised: {e}")
        return True

    except Exception as e:
        print(f"❌ WRONG EXCEPTION TYPE: {type(e).__name__}: {e}")
        return False


def main():
    print("🔧 Response Validator Fix Verification")
    print("=" * 50)

    success = test_exception_raising()

    print("\n" + "=" * 50)
    if success:
        print("🎉 VALIDATION BUG IS FIXED!")
    else:
        print("❌ Bug still exists")


if __name__ == "__main__":
    main()

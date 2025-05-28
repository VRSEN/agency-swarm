#!/usr/bin/env python3
"""
Direct test of Thread class validation functionality, bypassing Agency.
"""

from agency_swarm.agents import Agent
from agency_swarm.threads.thread import Thread
from agency_swarm.user import User


class TestAgent(Agent):
    def response_validator(self, message: str) -> str:
        print(f"✅ VALIDATOR CALLED: {repr(message[:50])}...")

        # Add stack trace to see what's calling this
        import traceback

        print("📍 STACK TRACE:")
        traceback.print_stack()

        if "VALIDATED" not in message:
            print(f"❌ VALIDATION FAILED: Missing VALIDATED")
            raise ValueError("Response must contain the word 'VALIDATED'.")
        print(f"✅ VALIDATION PASSED")
        return message


def test_direct_thread_validation():
    """Test Thread validation directly without Agency."""
    print("🧪 Testing Thread validation directly...")

    # Create agent with validator
    agent = TestAgent(
        name="TestAgent",
        description="Test agent",
        instructions="Test",
        validation_attempts=1,  # No retries - should raise exception
    )

    # Create thread directly
    user = User()
    thread = Thread(user, agent)

    print(f"🔍 Thread class: {type(thread)}")
    print(f"🔍 Thread module: {type(thread).__module__}")
    print(f"🔍 Has _validate_assistant_response: {hasattr(thread, '_validate_assistant_response')}")

    # Test the validation method directly
    print("📝 Testing _validate_assistant_response directly...")

    try:
        # This should raise an exception since the message doesn't contain "VALIDATED"
        print(f"🔍 About to call _validate_assistant_response with validation_attempts=1")
        result = thread._validate_assistant_response(
            recipient_agent=agent,
            last_message="Hello there!",  # Missing "VALIDATED"
            validation_attempts=1,  # Exceeds limit (1) - should raise exception
            yield_messages=False,
            additional_instructions=None,
            event_handler=None,
            tool_choice=None,
            response_format=None,
        )
        print(f"🔍 Method returned: {result}")

        print(f"❌ UNEXPECTED: No exception raised. Result: {result}")
        return False

    except ValueError as e:
        print(f"✅ SUCCESS: Exception properly raised: {e}")
        return True

    except Exception as e:
        print(f"❌ WRONG EXCEPTION: {type(e).__name__}: {e}")
        return False


def main():
    print("🔧 Direct Thread Validation Test")
    print("=" * 50)

    success = test_direct_thread_validation()

    print("\n" + "=" * 50)
    if success:
        print("🎉 THREAD VALIDATION FIX WORKS!")
    else:
        print("❌ Thread validation fix failed")


if __name__ == "__main__":
    main()

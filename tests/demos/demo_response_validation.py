#!/usr/bin/env python3
"""
Minimal test proving the validation feedback loop works.

This test verifies that:
1. Agent gets validation error message
2. Agent sees the error and corrects response
3. Conversation history shows the feedback loop
"""

from agency_swarm import Agency, Agent


def validation_function(message: str) -> str:
    """Validator that requires responses to contain 'FIXED'"""
    if "FIXED" not in message:
        raise ValueError("Your response must contain the word FIXED")
    return message


def test_validation_feedback_loop():
    """Minimal test proving agent receives and acts on validation errors."""

    print("🧪 Testing validation feedback loop...")

    # Agent that can learn from validation errors
    agent = Agent(
        name="TestAgent",
        description="Agent that learns from validation",
        instructions="Respond helpfully. If you receive an error message, follow its instructions exactly.",
    )

    # Set validation after creation
    agent.response_validator = validation_function
    agent.validation_attempts = 2

    agency = Agency([agent])

    # This should trigger validation failure, then correction
    response = agency.get_completion("Say hello briefly.")

    print(f"Final response: {response}")

    # Check if agent learned and included "FIXED"
    if "FIXED" in response:
        print("✅ SUCCESS: Agent received validation error and corrected response!")

        # Show the conversation to prove feedback loop
        print("\n📝 Conversation history (proving feedback loop):")
        messages = agency.main_thread.get_messages()
        for i, msg in enumerate(reversed(messages)):
            role_icon = "🤖" if msg.role == "assistant" else "👤"
            content = msg.content[0].text.value
            print(f"{i+1}. {role_icon} {msg.role}: {content}")

        return True
    else:
        print(f"❌ FAILED: Agent didn't correct response. Got: {response}")
        return False


if __name__ == "__main__":
    success = test_validation_feedback_loop()

    if success:
        print("\n🎉 PROOF: Validation feedback loop works!")
        print("✅ Agent receives validation errors")
        print("✅ Agent corrects responses based on validation")
    else:
        print("\n❌ FAILED: Validation feedback loop broken")

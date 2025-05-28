from agency_swarm import Agency, Agent


class LearningAgent(Agent):
    def response_validator(self, message: str) -> str:
        print(f"VALIDATOR DEBUG: Checking message: {repr(message[:50])}...")
        if "VALIDATED" not in message:
            error_msg = "Please include the word VALIDATED in your response."
            print(f"VALIDATOR DEBUG: Validation failed! Sending error: {error_msg}")
            raise ValueError(error_msg)
        print(f"VALIDATOR DEBUG: Validation passed! ✅")
        return message


def main():
    agent = LearningAgent(
        name="LearningAgent",
        description="An agent that learns from validation errors.",
        instructions="You are a helpful assistant. Respond naturally to user requests. If you receive an error message from the user, read it carefully and adjust your response accordingly.",
        validation_attempts=3,  # Allow 2 retries
    )
    agency = Agency([agent], temperature=0)

    print("=== Testing validation retry mechanism ===")
    print("Sending request that will likely fail validation initially...")

    response = agency.get_completion("Please respond with a simple greeting.")
    print(f"\nFinal response: {response}")

    # Show the conversation to see the retry mechanism
    print("\n=== Full Conversation History ===")
    messages = agency.main_thread.get_messages()
    for i, msg in enumerate(reversed(messages)):
        role_icon = "🤖" if msg.role == "assistant" else "👤"
        print(f"{role_icon} {msg.role.title()}: {msg.content[0].text.value}")
        print()


if __name__ == "__main__":
    main()

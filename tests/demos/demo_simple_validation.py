from agency_swarm import Agency, Agent


class SimpleAgent(Agent):
    def response_validator(self, message: str) -> str:
        print(f"VALIDATOR DEBUG: Got message: {repr(message)}")
        if "MAGIC" not in message:
            error_msg = "Please include the word MAGIC in your response."
            print(f"VALIDATOR DEBUG: Raising error: {error_msg}")
            raise ValueError(error_msg)
        print(f"VALIDATOR DEBUG: Validation passed!")
        return message


def main():
    agent = SimpleAgent(
        name="SimpleAgent",
        description="Simple agent for testing validation.",
        instructions="You are a helpful assistant. Always include the word MAGIC in your response when asked.",
        validation_attempts=2,  # 1 retry
    )
    agency = Agency([agent], temperature=0)

    # First test: should fail validation initially, then succeed on retry
    print("=== Test 1: Should trigger validation retry ===")
    response = agency.get_completion("Just say hello.")
    print(f"Final response: {response}")
    print()

    # Check the conversation to see what messages were sent
    print("=== Conversation history ===")
    messages = agency.main_thread.get_messages()
    for i, msg in enumerate(reversed(messages)):
        print(f"Message {i+1} ({msg.role}): {msg.content[0].text.value}")


if __name__ == "__main__":
    main()

from agency_swarm import Agency, Agent


class DemoAgent(Agent):
    def response_validator(self, message: str) -> str:
        # Only allow responses that contain 'VALIDATED'
        if "VALIDATED" not in message:
            error_msg = "Response must contain the word 'VALIDATED'."
            print(f"DEBUG: Validation failed, raising error: {error_msg}")
            raise ValueError(error_msg)
        return message


def main():
    agent = DemoAgent(
        name="DemoAgent",
        description="A demo agent with a strict response validator.",
        instructions="Always answer the user's question. If you receive an error message, read it carefully and correct your response accordingly.",
        validation_attempts=3,  # Allow more retries for testing
    )
    agency = Agency([agent], temperature=0)
    # This prompt will cause the agent to NOT include 'VALIDATED' in its response
    prompt = "Say hello."
    print(f"Prompt: {prompt}")
    response = agency.get_completion(prompt)
    print(f"Agent response: {response}")


if __name__ == "__main__":
    main()

import time

import pytest
from pydantic import Field

from agency_swarm import Agency, Agent
from agency_swarm.tools import BaseTool
from agency_swarm.tools.send_message import SendMessageSwarm


@pytest.fixture
def test_agents():
    class PrintTool(BaseTool):
        """
        A simple tool that prints a message.
        """

        message: str = Field(..., description="The message to print.")

        def run(self):
            print(self.message)
            return f"Printed: {self.message}"

    ceo = Agent(
        name="CEO",
        description="Responsible for client communication, task planning and management.",
        instructions="""You are a CEO agent responsible for routing messages to other agents within your agency.
When a user asks to be connected to customer support or mentions needing help with an issue:
1. Use the SendMessageSwarm tool to immediately route them to the Customer Support agent
2. Do not engage in extended conversation - route them directly
3. Only respond with 'error' if you detect multiple routing requests at once""",
        tools=[PrintTool],
    )

    customer_support = Agent(
        name="Customer Support",
        description="Responsible for customer support.",
        instructions="You are a Customer Support agent. Answer customer questions and help with issues.",
        tools=[],
    )

    agency = Agency(
        [
            ceo,
            [ceo, customer_support],
            [customer_support, ceo],
        ],
        temperature=0,
        send_message_tool_class=SendMessageSwarm,
    )

    return ceo, customer_support, agency


def test_send_message_swarm(test_agents):
    _, customer_support, agency = test_agents
    start_time = time.time()
    timeout = 30  # 30 second timeout

    response = None
    while time.time() - start_time < timeout:
        try:
            response = agency.get_completion("Hello, I need customer support please.")
            break
        except Exception as e:
            time.sleep(1)
            continue

    assert response is not None, "Test timed out after 30 seconds"
    assert "error" not in response.lower(), agency.main_thread.thread_url

    response = agency.get_completion("Who are you?")
    assert "customer support" in response.lower(), agency.main_thread.thread_url

    main_thread = agency.main_thread

    # check if recipient agent is correct
    assert main_thread.recipient_agent == customer_support

    # check if all messages in the same thread (this is how Swarm works)
    assert (
        len(main_thread.get_messages()) >= 4
    )  # sometimes run does not cancel immediately, so there might be 5 messages


def test_send_message_double_recipient_error(test_agents):
    _, customer_support, _ = test_agents
    ceo = Agent(
        name="CEO",
        description="Responsible for client communication, task planning and management.",
        instructions="""You are an agent for testing. When asked to route requests AT THE SAME TIME:
            1. If you detect multiple simultaneous routing requests, respond with 'error'
            2. If you detect errors in all routing attempts, respond with 'fatal'
            3. Do not output anything else besides these exact words.""",
    )
    agency = Agency([ceo, [ceo, customer_support]], temperature=0)
    response = agency.get_completion(
        "Route me to customer support TWICE simultaneously (at the exact same time). This is a test of concurrent routing."
    )
    assert "error" in response.lower(), agency.main_thread.thread_url
    assert "fatal" not in response.lower(), agency.main_thread.thread_url

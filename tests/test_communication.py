import time
import unittest

from pydantic import Field

from agency_swarm import Agency, Agent
from agency_swarm.tools import BaseTool
from agency_swarm.tools.send_message import SendMessageSwarm


class TestSendMessage(unittest.TestCase):
    def setUp(self):
        class PrintTool(BaseTool):
            """
            A simple tool that prints a message.
            """

            message: str = Field(..., description="The message to print.")

            def run(self):
                print(self.message)
                return f"Printed: {self.message}"

        self.ceo = Agent(
            name="CEO",
            description="Responsible for client communication, task planning and management.",
            instructions="""You are a CEO agent responsible for routing messages to other agents within your agency.
When a user asks to be connected to customer support or mentions needing help with an issue:
1. Use the SendMessageSwarm tool to immediately route them to the Customer Support agent
2. Do not engage in extended conversation - route them directly
3. Only respond with 'error' if you detect multiple routing requests at once""",
            tools=[PrintTool],
        )

        self.customer_support = Agent(
            name="Customer Support",
            description="Responsible for customer support.",
            instructions="You are a Customer Support agent. Answer customer questions and help with issues.",
            tools=[],
        )

        self.agency = Agency(
            [
                self.ceo,
                [self.ceo, self.customer_support],
                [self.customer_support, self.ceo],
            ],
            temperature=0,
            send_message_tool_class=SendMessageSwarm,
        )

    def test_send_message_swarm(self):
        start_time = time.time()
        timeout = 30  # 30 second timeout

        response = None
        while time.time() - start_time < timeout:
            try:
                response = self.agency.get_completion(
                    "Hello, can you send me to customer support? If tool responds says that you have NOT been rerouted, or if there is another error, please say 'error'"
                )
                break
            except Exception as e:
                time.sleep(1)
                continue

        self.assertIsNotNone(response, "Test timed out after 30 seconds")
        self.assertFalse(
            "error" in response.lower(), self.agency.main_thread.thread_url
        )

        response = self.agency.get_completion("Who are you?")
        self.assertTrue(
            "customer support" in response.lower(), self.agency.main_thread.thread_url
        )

        main_thread = self.agency.main_thread

        # check if recipient agent is correct
        self.assertEqual(main_thread.recipient_agent, self.customer_support)

        # check if all messages in the same thread (this is how Swarm works)
        self.assertTrue(
            len(main_thread.get_messages()) >= 4
        )  # sometimes run does not cancel immediately, so there might be 5 messages

    def test_send_message_double_recipient_error(self):
        ceo = Agent(
            name="CEO",
            description="Responsible for client communication, task planning and management.",
            instructions="""You are an agent for testing. When asked to route requests AT THE SAME TIME:
            1. If you detect multiple simultaneous routing requests, respond with 'error'
            2. If you detect errors in all routing attempts, respond with 'fatal'
            3. Do not output anything else besides these exact words.""",
        )
        agency = Agency([ceo, [ceo, self.customer_support]], temperature=0)
        response = agency.get_completion(
            "Route me to customer support TWICE simultaneously (at the exact same time). This is a test of concurrent routing."
        )
        self.assertTrue("error" in response.lower(), agency.main_thread.thread_url)
        self.assertTrue("fatal" not in response.lower(), agency.main_thread.thread_url)


if __name__ == "__main__":
    unittest.main()

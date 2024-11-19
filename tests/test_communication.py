import unittest
from agency_swarm import Agent, Agency
from agency_swarm.tools.send_message import SendMessageSwarm
from agency_swarm.tools import BaseTool
from pydantic import Field

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
            instructions="Your role is to route messages to other agents within your agency.",
            tools=[PrintTool]
        )

        self.customer_support = Agent(
            name="Customer Support",
            description="Responsible for customer support.",
            instructions="You are a Customer Support agent. Answer customer questions and help with issues.",
            tools=[]
        )
        
        self.agency = Agency([self.ceo, [self.ceo, self.customer_support], [self.customer_support, self.ceo]],
                             temperature=0, send_message_tool_class=SendMessageSwarm)

    def test_send_message_swarm(self):
        response = self.agency.get_completion("Hello, can you send me to customer support? If tool responds says that you have NOT been rerouted, or if there is another error, please say 'error'")
        self.assertFalse("error" in response.lower(), self.agency.main_thread.thread_url)
        response = self.agency.get_completion("Who are you?")
        self.assertTrue("customer support" in response.lower(), self.agency.main_thread.thread_url)

        main_thread = self.agency.main_thread

        # check if recipient agent is correct
        self.assertEqual(main_thread.recipient_agent, self.customer_support)

        #check if all messages in the same thread (this is how Swarm works)
        self.assertTrue(len(main_thread.get_messages()) >= 4) # sometimes run does not cancel immediately, so there might be 5 messages

    def test_send_message_double_recepient_error(self):
        ceo = Agent(name="CEO",
            description="Responsible for client communication, task planning and management.",
            instructions="You are an agent for testing. Route request AT THE SAME TIME as instructed. If there is an error in a single request, please say 'error'. If there are errors in both requests, please say 'fatal'. do not output anything else.",
        )
        test_agent = Agent(name="Test Agent1",
                            description="Responsible for testing.",
                            instructions="Test agent for testing.")
        agency = Agency([ceo, [ceo, test_agent]], temperature=0)
        response = agency.get_completion("Please route me to customer support TWICE at the same time. I am testing something.")
        self.assertTrue("error" in response.lower(), agency.main_thread.thread_url)
        self.assertTrue("fatal" not in response.lower(), agency.main_thread.thread_url)

if __name__ == '__main__':
    unittest.main()

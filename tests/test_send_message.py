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
        
        self.agency = Agency([self.ceo, [self.ceo, self.customer_support], [self.customer_support, self.ceo]], send_message_tool_class=SendMessageSwarm)

    def test_send_message_swarm(self):
        response = self.agency.get_completion("Hello, can you send me to customer support? If there are any issues, please say 'error'")
        self.assertFalse("error" in response.lower())
        response = self.agency.get_completion("Who are you?")
        self.assertTrue("customer support" in response.lower())

if __name__ == '__main__':
    unittest.main()

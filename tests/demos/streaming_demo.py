import sys
import unittest

from agency_swarm.lib.streaming import AgencyEventHandler
from typing_extensions import override

from agency_swarm import Agent, BaseTool
from agency_swarm.agency.agency import Agency

sys.path.insert(0, '../agency-swarm')


class StreamingTest(unittest.TestCase):
    def setUp(self):
        class TestTool(BaseTool):
            def run(self):
                return "Test Successful"

        self.ceo = Agent(name="ceo", instructions="You are a CEO of an agency made for testing purposes.",
                         model='gpt-3.5-turbo')
        self.test_agent1 = Agent(name="test_agent1", tools=[TestTool], model='gpt-3.5-turbo')
        self.test_agent2 = Agent(name="test_agent2", model='gpt-3.5-turbo')

        self.agency = Agency([
            self.ceo,
            [self.ceo, self.test_agent1, self.test_agent2],
            [self.ceo, self.test_agent2]
        ])

    def test_demo(self):
        self.agency.run_demo()


if __name__ == '__main__':
    unittest.main()

import time
import unittest

from agency_swarm import Agent, BaseTool
from agency_swarm.agency.agency import Agency
from agency_swarm.constants import DEFAULT_MODEL_MINI


class StreamingTest(unittest.TestCase):
    def setUp(self):
        class TestTool(BaseTool):
            def run(self):
                time.sleep(10)
                print("done")
                return "Test Successful"

        self.ceo = Agent(
            name="ceo",
            instructions="You are a CEO of an agency made for testing purposes.",
            model=DEFAULT_MODEL_MINI,
        )
        self.test_agent1 = Agent(
            name="test_agent1", tools=[TestTool], model=DEFAULT_MODEL_MINI
        )
        self.test_agent2 = Agent(name="test_agent2", model=DEFAULT_MODEL_MINI)

        self.agency = Agency(
            [
                self.ceo,
                [self.ceo, self.test_agent1, self.test_agent2],
                [self.ceo, self.test_agent2],
            ]
        )

    def test_demo(self):
        self.agency.demo_gradio()


if __name__ == "__main__":
    unittest.main()

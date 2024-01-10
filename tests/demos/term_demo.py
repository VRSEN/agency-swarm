import sys
import unittest

from agency_swarm import set_openai_key
from agency_swarm.agency.agency import Agency
from agency_swarm.threads import Thread
from tests.ceo.ceo import Ceo
from .test_agent.test_agent import TestAgent
from .test_agent2.test_agent2 import TestAgent2

sys.path.insert(0, '../agency-swarm')
import json


class MyTestCase(unittest.TestCase):
    def setUp(self):
        self.test_agent1 = TestAgent()
        self.test_agent2 = TestAgent2()
        self.ceo = Ceo()

        self.agency = Agency([
            self.ceo,
            [self.ceo, self.test_agent1, self.test_agent2],
            [self.ceo, self.test_agent2]
        ])

        def custom_serializer(obj):
            if isinstance(obj, Thread):
                return {"agent": obj.agent.name, "recipient_agent": obj.recipient_agent.name}
            # You can add more types here if needed
            raise TypeError(f"Type {type(obj)} not serializable")

        print(json.dumps(self.agency.agents_and_threads, indent=4, default=custom_serializer))

        print("Ceo Tools: ", self.agency.ceo.tools)

    def test_demo(self):
        self.agency.run_demo()


if __name__ == '__main__':
    unittest.main()

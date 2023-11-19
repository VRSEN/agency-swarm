import unittest

from agency_swarm import set_openai_key
from .test_agent.test_agent import TestAgent
import sys
import os
import json

sys.path.insert(0, '../agency_swarm')


class MyTestCase(unittest.TestCase):
    agent = None

    def setUp(self):
        set_openai_key("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")

    # it should create new settings file and init agent
    def test_init_agent(self):
        self.agent = TestAgent()
        self.assertTrue(self.agent.id)

        self.settings_path = self.agent.get_settings_path()
        self.assertTrue(os.path.exists(self.settings_path))

        # find assistant in settings by id
        with open(self.settings_path, 'r') as f:
            settings = json.load(f)
            for assistant_settings in settings:
                if assistant_settings['id'] == self.agent.id:
                    self.assertTrue(self.agent._check_parameters(assistant_settings))

    # it should load assistant from settings
    def test_load_agent(self):
        self.agent = TestAgent()
        agent2 = TestAgent()
        self.assertEqual(self.agent.id, agent2.id)

    def tearDown(self):
        # delete assistant from openai
        self.agent.delete_assistant()

        os.remove(self.agent.get_settings_path())

        pass


if __name__ == '__main__':
    unittest.main()

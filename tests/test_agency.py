import inspect
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, '../agency-swarm')
from agency_swarm.util import create_agent_template

from agency_swarm import set_openai_key, Agent, Agency


class AgencyTest(unittest.TestCase):
    agency = None
    agent2 = None
    agent1 = None
    ceo = None
    num_schemas = None
    num_files = None

    # testing loading agents from db
    loaded_thread_ids = None
    loaded_agents_settings = None
    settings_callbacks = None
    threads_callbacks = None


    @classmethod
    def setUpClass(cls):
        cls.num_files = 0
        cls.num_schemas = 0
        cls.ceo = None
        cls.agent1 = None
        cls.agent2 = None
        cls.agency = None

        # testing loading agents from db
        cls.loaded_thread_ids = {}
        cls.loaded_agents_settings = []

        def save_settings_callback(settings):
            cls.loaded_agents_settings = settings

        cls.settings_callbacks = {
            "load": lambda: cls.loaded_agents_settings,
            "save": save_settings_callback,
        }

        def save_thread_callback(agents_and_thread_ids):
            cls.loaded_thread_ids = agents_and_thread_ids

        cls.threads_callbacks = {
            "load": lambda: cls.loaded_thread_ids,
            "save": save_thread_callback,
        }


        if not os.path.exists("./test_agents"):
            os.mkdir("./test_agents")
        else:
            shutil.rmtree("./test_agents")
            os.mkdir("./test_agents")

        # create init file
        with open("./test_agents/__init__.py", "w") as f:
            f.write("")

        # create agent templates in test_agents
        create_agent_template("CEO", "CEO Test Agent", path="./test_agents",
                              instructions="Your task is to tell TestAgent1 to say test to another test agent. If the "
                                           "agent, does not respond or something goes wrong please say 'error' and "
                                           "nothing else. Otherwise say 'success' and nothing else.")
        create_agent_template("TestAgent1", "Test Agent 1", path="./test_agents",
                              instructions="Your task is to say test to another test agent using SendMessage tool. "
                                           "If the agent, does not "
                                           "respond or something goes wrong please say 'error' and nothing else. "
                                            "Otherwise say 'success' and nothing else.")
        create_agent_template("TestAgent2", "Test Agent 2", path="./test_agents",
                              instructions="Please respond to the user that test was a success.")

        sys.path.insert(0, './test_agents')

        # copy files from data/files to test_agents/TestAgent1/files
        for file in os.listdir("./data/files"):
            shutil.copyfile("./data/files/" + file, "./test_agents/TestAgent1/files/" + file)
            cls.num_files += 1

        # copy schemas from data/schemas to test_agents/TestAgent2/schemas
        for file in os.listdir("./data/schemas"):
            shutil.copyfile("./data/schemas/" + file, "./test_agents/TestAgent2/schemas/" + file)
            cls.num_schemas += 1

        from test_agents import CEO, TestAgent1, TestAgent2
        cls.ceo = CEO()
        cls.agent1 = TestAgent1()
        cls.agent2 = TestAgent2()

    def test_1_init_agency(self):
        """it should initialize agency with agents"""
        self.__class__.agency = Agency([
            self.__class__.ceo,
            [self.__class__.ceo, self.__class__.agent1],
            [self.__class__.agent1, self.__class__.agent2]],
            shared_instructions="This is a shared instruction",
            settings_callbacks=self.__class__.settings_callbacks,
            threads_callbacks=self.__class__.threads_callbacks,
        )

        self.check_all_agents_settings()

    def test_2_load_agent(self):
        """it should load existing assistant from settings"""
        from test_agents import TestAgent1
        agent3 = TestAgent1()
        agent3.add_shared_instructions(self.__class__.agency.shared_instructions)
        agent3.tools = self.__class__.agent1.tools
        agent3 = agent3.init_oai()

        print("agent3", agent3.assistant.model_dump())
        print("agent1", self.__class__.agent1.assistant.model_dump())

        self.assertTrue(self.__class__.agent1.id == agent3.id)

        # check that assistant settings match
        self.assertTrue(agent3._check_parameters(self.__class__.agent1.assistant.model_dump()))

        self.check_agent_settings(agent3)

    def test_3_load_agent_id(self):
        """it should load existing assistant from id"""
        from test_agents import TestAgent1
        agent3 = Agent(id=self.__class__.agent1.id)
        agent3.tools = self.__class__.agent1.tools
        agent3 = agent3.init_oai()

        print("agent3", agent3.assistant.model_dump())
        print("agent1", self.__class__.agent1.assistant.model_dump())

        self.assertTrue(self.__class__.agent1.id == agent3.id)

        # check that assistant settings match
        self.assertTrue(agent3._check_parameters(self.__class__.agent1.assistant.model_dump()))

        self.check_agent_settings(agent3)

    def test_4_agent_communication(self):
        """it should communicate between agents"""
        print("TestAgent1 tools", self.__class__.agent1.tools)
        message = self.__class__.agency.get_completion("Please tell TestAgent1 to say test to TestAgent2.", yield_messages=False)

        self.assertFalse('error' in message.lower())

        for agent_name, threads in self.__class__.agency.agents_and_threads.items():
            for other_agent_name, thread in threads.items():
                self.assertTrue(thread.id in self.__class__.loaded_thread_ids[agent_name][other_agent_name])

        for agent in self.__class__.agency.agents:
            self.assertTrue(agent.id in [settings['id'] for settings in self.__class__.loaded_agents_settings])

    def test_5_load_from_db(self):
        """it should load agents from db"""
        os.rename("settings.json", "settings2.json")

        previous_loaded_thread_ids = self.__class__.loaded_thread_ids
        previous_loaded_agents_settings = self.__class__.loaded_agents_settings

        from test_agents import CEO, TestAgent1, TestAgent2
        agent1 = TestAgent1()
        agent2 = TestAgent2()
        ceo = CEO()

        # check that agents are loaded
        agency = Agency([
            ceo,
            [ceo, agent1],
            [agent1, agent2]],
            shared_instructions="This is a shared instruction",
            settings_callbacks=self.__class__.settings_callbacks,
            threads_callbacks=self.__class__.threads_callbacks,
        )

        os.remove("settings.json")
        os.rename("settings2.json", "settings.json")

        self.check_all_agents_settings()

        # check that threads are the same
        for agent_name, threads in agency.agents_and_threads.items():
            for other_agent_name, thread in threads.items():
                self.assertTrue(thread.id in self.__class__.loaded_thread_ids[agent_name][other_agent_name])
                self.assertTrue(thread.id in previous_loaded_thread_ids[agent_name][other_agent_name])

        # check that agents are the same
        for agent in agency.agents:
            self.assertTrue(agent.id in [settings['id'] for settings in self.__class__.loaded_agents_settings])
            self.assertTrue(agent.id in [settings['id'] for settings in previous_loaded_agents_settings])

    # --- Helper methods ---

    def get_class_folder_path(self):
        return os.path.abspath(os.path.dirname(inspect.getfile(self.__class__)))

    def check_agent_settings(self, agent):
        try:
            settings_path = agent.get_settings_path()
            self.assertTrue(os.path.exists(settings_path))
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                for assistant_settings in settings:
                    if assistant_settings['id'] == agent.id:
                        self.assertTrue(agent._check_parameters(assistant_settings))

            assistant = agent.assistant
            self.assertTrue(assistant)
            self.assertTrue(agent._check_parameters(assistant.model_dump()))
            if agent.name == "TestAgent1":
                self.assertTrue(len(assistant.file_ids) == self.__class__.num_files)
                for file_id in assistant.file_ids:
                    self.assertTrue(file_id in agent.file_ids)
                # check retrieval tools is there
                self.assertTrue(len(assistant.tools) == 2)
                self.assertTrue(len(agent.tools) == 2)
                self.assertTrue(assistant.tools[0].type == "retrieval")
                self.assertTrue(assistant.tools[1].type == "function")
                self.assertTrue(assistant.tools[1].function.name == "SendMessage")
            elif agent.name == "TestAgent2":
                self.assertTrue(len(assistant.tools) == self.__class__.num_schemas)
                for tool in assistant.tools:
                    self.assertTrue(tool.type == "function")
                    self.assertTrue(tool.function.name in [tool.__name__ for tool in agent.tools])
            elif agent.name == "CEO":
                self.assertTrue(len(assistant.file_ids) == 0)
                self.assertTrue(len(assistant.tools) == 1)
        except Exception as e:
            print("Error checking agent settings ", agent.name)
            raise e

    def check_all_agents_settings(self):
        self.check_agent_settings(self.__class__.ceo)
        self.check_agent_settings(self.__class__.agent1)
        self.check_agent_settings(self.__class__.agent2)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree("./test_agents")
        os.remove("./settings.json")
        cls.ceo.delete()
        cls.agent1.delete()
        cls.agent2.delete()


if __name__ == '__main__':
    unittest.main()

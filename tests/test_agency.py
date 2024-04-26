import inspect
import json
import os
import shutil
import sys
import time
import unittest

from openai.types.beta.threads.runs import ToolCall

from agency_swarm.tools import CodeInterpreter, FileSearch

sys.path.insert(0, '../agency-swarm')
from agency_swarm.util import create_agent_template

from agency_swarm import set_openai_key, Agent, Agency, AgencyEventHandler, get_openai_client
from typing_extensions import override
from agency_swarm.tools import BaseTool

os.environ["DEBUG_MODE"] = "True"

class AgencyTest(unittest.TestCase):
    TestTool = None
    agency = None
    agent2 = None
    agent1 = None
    ceo = None
    num_schemas = None
    num_files = None
    client = None

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
        cls.client = get_openai_client()

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
                                           "nothing else. Otherwise say 'success' and nothing else.",
                              include_example_tool=True)
        create_agent_template("TestAgent1", "Test Agent 1", path="./test_agents",
                              instructions="Your task is to say test to another test agent using SendMessage tool. "
                                           "If the agent, does not "
                                           "respond or something goes wrong please say 'error' and nothing else. "
                                           "Otherwise say 'success' and nothing else.", code_interpreter=True,
                              include_example_tool=False)
        create_agent_template("TestAgent2", "Test Agent 2", path="./test_agents",
                              instructions="After using TestTool, please respond to the user that test was a success in JSON format. You can use the following format: {'test': 'success'}.",
                              include_example_tool=False)

        sys.path.insert(0, './test_agents')

        # copy files from data/files to test_agents/TestAgent1/files
        for file in os.listdir("./data/files"):
            shutil.copyfile("./data/files/" + file, "./test_agents/TestAgent1/files/" + file)
            cls.num_files += 1

        # copy schemas from data/schemas to test_agents/TestAgent2/schemas
        for file in os.listdir("./data/schemas"):
            shutil.copyfile("./data/schemas/" + file, "./test_agents/TestAgent2/schemas/" + file)
            cls.num_schemas += 1

        class TestTool(BaseTool):
            """
            A simple test tool that returns "Test Successful" to demonstrate the functionality of a custom tool within the Agency Swarm framework.
            """

            # This tool does not require any input fields, but you can define them similarly for other tools.

            def run(self):
                """
                Executes the test tool's main functionality. In this case, it simply returns a success message.
                """
                self.shared_state.set("test_tool_used", True)

                return "Test Successful"

        cls.TestTool = TestTool

        from test_agents.CEO import CEO
        from test_agents.TestAgent1 import TestAgent1
        from test_agents.TestAgent2 import TestAgent2
        cls.agent1 = TestAgent1()
        cls.agent1.add_tool(FileSearch)
        cls.agent1.truncation_strategy = {
            "type": "last_messages",
            "last_messages": 10
        }

        cls.agent2 = TestAgent2()
        cls.agent2.add_tool(cls.TestTool)

        cls.agent2.response_format = {
            "type": "json_object",
        }

        cls.ceo = CEO()
        cls.ceo.examples = [
            {
                "role": "user",
                "content": "Hi!"
            },
            {
                "role": "assistant",
                "content": "Hi! I am the CEO. I am here to help you with your testing. Please tell me who to send message to."
            }
        ]

        cls.ceo.max_completion_tokens = 100

    def test_1_init_agency(self):
        """it should initialize agency with agents"""
        self.__class__.agency = Agency([
            self.__class__.ceo,
            [self.__class__.ceo, self.__class__.agent1],
            [self.__class__.agent1, self.__class__.agent2]],
            shared_instructions="This is a shared instruction",
            settings_callbacks=self.__class__.settings_callbacks,
            threads_callbacks=self.__class__.threads_callbacks,
            temperature=0,
        )

        self.check_all_agents_settings()

    def test_2_load_agent(self):
        """it should load existing assistant from settings"""
        from test_agents.TestAgent1 import TestAgent1
        agent3 = TestAgent1()
        agent3.add_shared_instructions(self.__class__.agency.shared_instructions)
        agent3.tools = self.__class__.agent1.tools
        agent3.top_p = self.__class__.agency.top_p
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
        message = self.__class__.agency.get_completion("Please tell TestAgent1 to say test to TestAgent2.",
                                                       tool_choice={"type": "function", "function": {"name": "SendMessage"}})

        self.assertFalse('error' in message.lower())

        for agent_name, threads in self.__class__.agency.agents_and_threads.items():
            for other_agent_name, thread in threads.items():
                self.assertTrue(thread.id in self.__class__.loaded_thread_ids[agent_name][other_agent_name])

        for agent in self.__class__.agency.agents:
            self.assertTrue(agent.id in [settings['id'] for settings in self.__class__.loaded_agents_settings])

        # assistants v2 checks
        main_thread = self.__class__.agency.main_thread
        main_thread_id = main_thread.id

        thread_messages = self.__class__.client.beta.threads.messages.list(main_thread_id, limit=100, order="asc")

        self.assertTrue(len(thread_messages.data) == 4)

        self.assertTrue(thread_messages.data[0].content[0].text.value == "Hi!")

        run = main_thread.run
        self.assertTrue(run.max_prompt_tokens == self.__class__.ceo.max_prompt_tokens)
        self.assertTrue(run.max_completion_tokens == self.__class__.ceo.max_completion_tokens)
        self.assertTrue(run.tool_choice.type == "function")

        agent1_thread = self.__class__.agency.agents_and_threads[self.__class__.ceo.name][self.__class__.agent1.name]

        agent1_thread_id = agent1_thread.id

        agent1_thread_messages = self.__class__.client.beta.threads.messages.list(agent1_thread_id, limit=100)

        self.assertTrue(len(agent1_thread_messages.data) == 2)

        agent1_run = agent1_thread.run

        self.assertTrue(agent1_run.truncation_strategy.type == "last_messages")
        self.assertTrue(agent1_run.truncation_strategy.last_messages == 10)

        agent2_thread = self.__class__.agency.agents_and_threads[self.__class__.agent1.name][self.__class__.agent2.name]

        agent2_message = agent2_thread._get_last_message_text()

        try:
            json.loads(agent2_message)
        except json.JSONDecodeError as e:
            self.assertTrue(False)

    def test_5_agent_communication_stream(self):
        """it should communicate between agents using streaming"""
        print("TestAgent1 tools", self.__class__.agent1.tools)

        test_tool_used = False
        test_agent2_used = False

        class EventHandler(AgencyEventHandler):
            @override
            def on_text_created(self, text) -> None:
                # get the name of the agent that is sending the message
                if self.recipient_agent_name == "TestAgent2":
                    nonlocal test_agent2_used
                    test_agent2_used = True

            def on_tool_call_done(self, tool_call: ToolCall) -> None:
                if tool_call.function.name == "TestTool":
                    nonlocal test_tool_used
                    test_tool_used = True

        message = self.__class__.agency.get_completion_stream(
            "Please tell TestAgent1 to tell TestAgent 2 to use test tool.",
            event_handler=EventHandler,
            additional_instructions="Your message to TestAgent1 should be exactly as follows: "
                                    "'Please tell TestAgent2 to use test tool.'",
            tool_choice={"type": "function", "function": {"name": "SendMessage"}})

        # self.assertFalse('error' in message.lower())

        self.assertTrue(test_tool_used)
        self.assertTrue(test_agent2_used)

        self.assertTrue(self.__class__.TestTool.shared_state.get("test_tool_used"))

        for agent_name, threads in self.__class__.agency.agents_and_threads.items():
            for other_agent_name, thread in threads.items():
                self.assertTrue(thread.id in self.__class__.loaded_thread_ids[agent_name][other_agent_name])

        for agent in self.__class__.agency.agents:
            self.assertTrue(agent.id in [settings['id'] for settings in self.__class__.loaded_agents_settings])

    def test_6_load_from_db(self):
        """it should load agents from db"""
        # os.rename("settings.json", "settings2.json")

        previous_loaded_thread_ids = self.__class__.loaded_thread_ids
        previous_loaded_agents_settings = self.__class__.loaded_agents_settings

        from test_agents.CEO import CEO
        from test_agents.TestAgent1 import TestAgent1
        from test_agents.TestAgent2 import TestAgent2
        agent1 = TestAgent1()
        agent1.add_tool(FileSearch)

        agent1.truncation_strategy = {
            "type": "last_messages",
            "last_messages": 10
        }

        agent2 = TestAgent2()
        agent2.add_tool(self.__class__.TestTool)

        agent2.response_format = {
            "type": "json_object",
        }

        ceo = CEO()

        # check that agents are loaded
        agency = Agency([
            ceo,
            [ceo, agent1],
            [agent1, agent2]],
            shared_instructions="This is a shared instruction",
            settings_path="./settings2.json",
            settings_callbacks=self.__class__.settings_callbacks,
            threads_callbacks=self.__class__.threads_callbacks,
            temperature=0,
        )

        # check that settings are the same
        self.assertTrue(len(agency.agents) == len(self.__class__.agency.agents))

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

    def test_7_init_async_agency(self):
        """it should initialize agency with agents"""
        # reset loaded thread ids
        self.__class__.loaded_thread_ids = {}

        self.__class__.agency = Agency([
            self.__class__.ceo,
            [self.__class__.ceo, self.__class__.agent1],
            [self.__class__.agent1, self.__class__.agent2]],
            shared_instructions="",
            settings_callbacks=self.__class__.settings_callbacks,
            threads_callbacks=self.__class__.threads_callbacks,
            async_mode='threading',
            temperature=0,
        )

        self.check_all_agents_settings(True)

    def test_8_async_agent_communication(self):
        """it should communicate between agents asynchronously"""
        print("TestAgent1 tools", self.__class__.agent1.tools)
        self.__class__.agency.get_completion("Please tell TestAgent2 hello.",
                                             tool_choice={"type": "function", "function": {"name": "SendMessage"}},
                                             recipient_agent=self.__class__.agent1)

        time.sleep(10)

        message = self.__class__.agency.get_completion(
            "Please check response. If output includes `TestAgent2's Response`, say 'success'. If the function output does not include `TestAgent2's Response`, or if you get a System Notification, or an error instead, say 'error'.",
            tool_choice={"type": "function", "function": {"name": "GetResponse"}},
            recipient_agent=self.__class__.agent1)

        if 'error' in message.lower():
            print(self.__class__.agency.get_completion("Explain why you said error."))
            self.assertFalse('error' in message.lower())

        for agent_name, threads in self.__class__.agency.agents_and_threads.items():
            for other_agent_name, thread in threads.items():
                self.assertTrue(thread.id in self.__class__.loaded_thread_ids[agent_name][other_agent_name])

        for agent in self.__class__.agency.agents:
            self.assertTrue(agent.id in [settings['id'] for settings in self.__class__.loaded_agents_settings])

    # --- Helper methods ---

    def get_class_folder_path(self):
        return os.path.abspath(os.path.dirname(inspect.getfile(self.__class__)))

    def check_agent_settings(self, agent, async_mode=False):
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
                num_tools = 3 if not async_mode else 4

                self.assertTrue(len(assistant.tool_resources.model_dump()['code_interpreter']['file_ids']) == 3)
                self.assertTrue(len(assistant.tool_resources.model_dump()['file_search']['vector_store_ids']) == 1)

                vector_store_id = assistant.tool_resources.model_dump()['file_search']['vector_store_ids'][0]
                vector_store_files = agent.client.beta.vector_stores.files.list(
                    vector_store_id=vector_store_id
                )

                file_ids = [file.id for file in vector_store_files.data]

                self.assertTrue(len(file_ids) == 5)
                # check retrieval tools is there
                self.assertTrue(len(assistant.tools) == num_tools)
                self.assertTrue(len(agent.tools) == num_tools)
                self.assertTrue(assistant.tools[0].type == "code_interpreter")
                self.assertTrue(assistant.tools[1].type == "file_search")
                self.assertTrue(assistant.tools[2].type == "function")
                self.assertTrue(assistant.tools[2].function.name == "SendMessage")
                if async_mode:
                    self.assertTrue(assistant.tools[3].type == "function")
                    self.assertTrue(assistant.tools[3].function.name == "GetResponse")
            elif agent.name == "TestAgent2":
                self.assertTrue(len(assistant.tools) == self.__class__.num_schemas + 1)
                for tool in assistant.tools:
                    self.assertTrue(tool.type == "function")
                    self.assertTrue(tool.function.name in [tool.__name__ for tool in agent.tools])
            elif agent.name == "CEO":
                num_tools = 1 if not async_mode else 2
                self.assertFalse(assistant.tool_resources.code_interpreter)
                self.assertFalse(assistant.tool_resources.file_search)
                self.assertTrue(len(assistant.tools) == num_tools)
            else:
                pass
        except Exception as e:
            print("Error checking agent settings ", agent.name)
            raise e

    def check_all_agents_settings(self, async_mode=False):
        self.check_agent_settings(self.__class__.ceo, async_mode=async_mode)
        self.check_agent_settings(self.__class__.agent1, async_mode=async_mode)
        self.check_agent_settings(self.__class__.agent2, async_mode=async_mode)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree("./test_agents")
        os.remove("./settings.json")
        cls.agency.delete()


if __name__ == '__main__':
    unittest.main()

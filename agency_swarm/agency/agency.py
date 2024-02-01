import inspect
import json
import os
import uuid
from enum import Enum
from typing import List, TypedDict, Callable, Any, Dict, Literal

from pydantic import Field, field_validator
from rich.console import Console

from agency_swarm.agents import Agent
from agency_swarm.threads import Thread
from agency_swarm.tools import BaseTool
from agency_swarm.user import User

console = Console()


class SettingsCallbacks(TypedDict):
    load: Callable[[], List[Dict]]
    save: Callable[[List[Dict]], Any]


class ThreadsCallbacks(TypedDict):
    load: Callable[[], Dict]
    save: Callable[[Dict], Any]


class Agency:
    ThreadType = Thread
    send_message_tool_description = """Use this tool for synchronous communication with other agents within your agency. For ongoing dialogue, resend messages to specific agents. Communication is synchronous, without post-response tasks. Relay agent responses to the user, who lacks direct access. Continue using the tool for continuous interaction until task completion."""
    send_message_tool_description_async = """Use this tool for asynchronous communication with other agents within your agency. Initiate tasks by messaging, and check status and responses later with the 'GetResponse' tool. Relay responses to the user, who instructs on status checks. Continue until task completion."""

    def __init__(self, agency_chart: List, shared_instructions: str = "", shared_files: List = None,
                 async_mode: Literal['threading'] = None,
                 settings_callbacks: SettingsCallbacks = None, threads_callbacks: ThreadsCallbacks = None):
        """
        Initializes the Agency object, setting up agents, threads, and core functionalities.

        Parameters:
        agency_chart: The structure defining the hierarchy and interaction of agents within the agency.
        shared_instructions (str, optional): A path to a file containing shared instructions for all agents. Defaults to an empty string.
        shared_files (list, optional): A list of folder paths with files containing shared resources for all agents. Defaults to an empty list.
        settings_callbacks (SettingsCallbacks, optional): A dictionary containing functions to load and save settings for the agency. The keys must be "load" and "save". Both values must be defined. Defaults to None.
        threads_callbacks (ThreadsCallbacks, optional): A dictionary containing functions to load and save threads for the agency. The keys must be "load" and "save". Both values must be defined. Defaults to None.

        This constructor initializes various components of the Agency, including CEO, agents, threads, and user interactions. It parses the agency chart to set up the organizational structure and initializes the messaging tools, agents, and threads necessary for the operation of the agency. Additionally, it prepares a main thread for user interactions.
        """
        self.async_mode = async_mode
        if self.async_mode == "threading":
            from agency_swarm.threads.thread_async import ThreadAsync
            self.ThreadType = ThreadAsync

        self.ceo = None
        self.agents = []
        self.agents_and_threads = {}
        self.shared_files = shared_files if shared_files else []
        self.settings_callbacks = settings_callbacks
        self.threads_callbacks = threads_callbacks

        if os.path.isfile(os.path.join(self.get_class_folder_path(), shared_instructions)):
            self._read_instructions(os.path.join(self.get_class_folder_path(), shared_instructions))
        elif os.path.isfile(shared_instructions):
            self._read_instructions(shared_instructions)
        else:
            self.shared_instructions = shared_instructions

        self._parse_agency_chart(agency_chart)
        self._create_special_tools()
        self._init_agents()
        self._init_threads()

        self.user = User()
        self.main_thread = Thread(self.user, self.ceo)

    def get_completion(self, message: str, message_files=None, yield_messages=True):
        """
        Retrieves the completion for a given message from the main thread.

        Parameters:
        message (str): The message for which completion is to be retrieved.
        message_files (list, optional): A list of file ids to be sent as attachments with the message. Defaults to None.
        yield_messages (bool, optional): Flag to determine if intermediate messages should be yielded. Defaults to True.

        Returns:
        Generator or final response: Depending on the 'yield_messages' flag, this method returns either a generator yielding intermediate messages or the final response from the main thread.
        """
        gen = self.main_thread.get_completion(message=message, message_files=message_files,
                                              yield_messages=yield_messages)

        if not yield_messages:
            while True:
                try:
                    next(gen)
                except StopIteration as e:
                    return e.value

        return gen

    def demo_gradio(self, height=600, dark_mode=True, share=False):
        """
        Launches a Gradio-based demo interface for the agency chatbot.

        Parameters:
        height (int, optional): The height of the chatbot widget in the Gradio interface. Default is 600.
        dark_mode (bool, optional): Flag to determine if the interface should be displayed in dark mode. Default is True.
        share (bool, optional): Flag to determine if the interface should be shared publicly. Default is False.
        This method sets up and runs a Gradio interface, allowing users to interact with the agency's chatbot. It includes a text input for the user's messages and a chatbot interface for displaying the conversation. The method handles user input and chatbot responses, updating the interface dynamically.
        """
        try:
            import gradio as gr
        except ImportError:
            raise Exception("Please install gradio: pip install gradio")

        js = """function () {
          gradioURL = window.location.href
          if (!gradioURL.endsWith('?__theme={theme}')) {
            window.location.replace(gradioURL + '?__theme={theme}');
          }
        }"""

        if dark_mode:
            js = js.replace("{theme}", "dark")
        else:
            js = js.replace("{theme}", "light")

        with gr.Blocks(js=js) as demo:
            chatbot = gr.Chatbot(height=height)
            msg = gr.Textbox()

            def user(user_message, history):
                # Append the user message with a placeholder for bot response
                user_message = "👤 User: " + user_message.strip()
                return "", history + [[user_message, None]]

            def bot(history):
                # Replace this with your actual chatbot logic
                gen = self.get_completion(message=history[-1][0])

                try:
                    # Yield each message from the generator
                    for bot_message in gen:
                        if bot_message.sender_name.lower() == "user":
                            continue

                        message = bot_message.get_sender_emoji() + " " + bot_message.get_formatted_content()

                        history.append((None, message))
                        yield history
                except StopIteration:
                    # Handle the end of the conversation if necessary
                    pass

            # Chain the events
            msg.submit(user, [msg, chatbot], [msg, chatbot], queue=False).then(
                bot, chatbot, chatbot
            )

            # Enable queuing for streaming intermediate outputs
            demo.queue()

        # Launch the demo
        demo.launch(share=share)
        return demo

    def run_demo(self):
        """
        Runs a demonstration of the agency's capabilities in an interactive command line interface.

        This function continuously prompts the user for input and displays responses from the agency's main thread. It leverages the generator pattern for asynchronous message processing.

        Output:
        Outputs the responses from the agency's main thread to the command line.
        """
        while True:
            console.rule()
            text = input("USER: ")

            try:
                gen = self.main_thread.get_completion(message=text)
                while True:
                    message = next(gen)
                    message.cprint()
            except StopIteration as e:
                pass

    def get_customgpt_schema(self, url: str):
        """Returns the OpenAPI schema for the agency from the CEO agent, that you can use to integrate with custom gpts.

        Parameters:
            url (str): Your server url where the api will be hosted.
        """

        return self.ceo.get_openapi_schema(url)

    def plot_agency_chart(self):
        pass

    def _init_agents(self):
        """
        Initializes all agents in the agency with unique IDs, shared instructions, and OpenAI models.

        This method iterates through each agent in the agency, assigns a unique ID, adds shared instructions, and initializes the OpenAI models for each agent.

        There are no input parameters.

        There are no output parameters as this method is used for internal initialization purposes within the Agency class.
        """
        if self.settings_callbacks:
            loaded_settings = self.settings_callbacks["load"]()
            with open(self.agents[0].get_settings_path(), 'w') as f:
                json.dump(loaded_settings, f, indent=4)

        for agent in self.agents:
            if "temp_id" in agent.id:
                agent.id = None
            agent.add_shared_instructions(self.shared_instructions)

            if self.shared_files:
                if isinstance(agent.files_folder, str):
                    agent.files_folder = [agent.files_folder]
                    agent.files_folder += self.shared_files
                elif isinstance(agent.files_folder, list):
                    agent.files_folder += self.shared_files

            agent.init_oai()

        if self.settings_callbacks:
            with open(self.agents[0].get_settings_path(), 'r') as f:
                settings = f.read()
            settings = json.loads(settings)
            self.settings_callbacks["save"](settings)

    def _init_threads(self):
        """
        Initializes threads for communication between agents within the agency.

        This method creates Thread objects for each pair of interacting agents as defined in the agents_and_threads attribute of the Agency. Each thread facilitates communication and task execution between an agent and its designated recipient agent.

        No input parameters.

        Output Parameters:
        This method does not return any value but updates the agents_and_threads attribute with initialized Thread objects.
        """
        # load thread ids
        loaded_thread_ids = {}
        if self.threads_callbacks:
            loaded_thread_ids = self.threads_callbacks["load"]()

        for agent_name, threads in self.agents_and_threads.items():
            for other_agent, items in threads.items():
                self.agents_and_threads[agent_name][other_agent] = self.ThreadType(
                    self.get_agent_by_name(items["agent"]),
                    self.get_agent_by_name(
                        items["recipient_agent"]))

                if agent_name in loaded_thread_ids and other_agent in loaded_thread_ids[agent_name]:
                    self.agents_and_threads[agent_name][other_agent].id = loaded_thread_ids[agent_name][other_agent]
                elif self.threads_callbacks:
                    self.agents_and_threads[agent_name][other_agent].init_thread()

        # save thread ids
        if self.threads_callbacks:
            loaded_thread_ids = {}
            for agent_name, threads in self.agents_and_threads.items():
                loaded_thread_ids[agent_name] = {}
                for other_agent, thread in threads.items():
                    loaded_thread_ids[agent_name][other_agent] = thread.id

            self.threads_callbacks["save"](loaded_thread_ids)

    def _parse_agency_chart(self, agency_chart):
        """
        Parses the provided agency chart to initialize and organize agents within the agency.

        Parameters:
        agency_chart: A structure representing the hierarchical organization of agents within the agency.
                    It can contain Agent objects and lists of Agent objects.

        This method iterates through each node in the agency chart. If a node is an Agent, it is set as the CEO if not already assigned.
        If a node is a list, it iterates through the agents in the list, adding them to the agency and establishing communication
        threads between them. It raises an exception if the agency chart is invalid or if multiple CEOs are defined.
        """
        for node in agency_chart:
            if isinstance(node, Agent):
                if self.ceo:
                    raise Exception("Only 1 ceo is supported for now.")
                self.ceo = node
                self._add_agent(self.ceo)

            elif isinstance(node, list):
                for i, agent in enumerate(node):
                    if not isinstance(agent, Agent):
                        raise Exception("Invalid agency chart.")

                    index = self._add_agent(agent)

                    if i == len(node) - 1:
                        continue

                    if agent.name not in self.agents_and_threads.keys():
                        self.agents_and_threads[agent.name] = {}

                    for other_agent in node:
                        if other_agent.name == agent.name:
                            continue
                        if other_agent.name not in self.agents_and_threads[agent.name].keys():
                            self.agents_and_threads[agent.name][other_agent.name] = {
                                "agent": agent.name,
                                "recipient_agent": other_agent.name,
                            }

            else:
                raise Exception("Invalid agency chart.")

    def _add_agent(self, agent):
        """
        Adds an agent to the agency, assigning a temporary ID if necessary.

        Parameters:
        agent (Agent): The agent to be added to the agency.

        Returns:
        int: The index of the added agent within the agency's agents list.

        This method adds an agent to the agency's list of agents. If the agent does not have an ID, it assigns a temporary unique ID. It checks for uniqueness of the agent's name before addition. The method returns the index of the agent in the agency's agents list, which is used for referencing the agent within the agency.
        """
        if not agent.id:
            # assign temp id
            agent.id = "temp_id_" + str(uuid.uuid4())
        if agent.id not in self.get_agent_ids():
            if agent.name in self.get_agent_names():
                raise Exception("Agent names must be unique.")
            self.agents.append(agent)
            return len(self.agents) - 1
        else:
            return self.get_agent_ids().index(agent.id)

    def _read_instructions(self, path):
        """
        Reads shared instructions from a specified file and stores them in the agency.

        Parameters:
        path (str): The file path from which to read the shared instructions.

        This method opens the file located at the given path, reads its contents, and stores these contents in the 'shared_instructions' attribute of the agency. This is used to provide common guidelines or instructions to all agents within the agency.
        """
        path = path
        with open(path, 'r') as f:
            self.shared_instructions = f.read()

    def _create_special_tools(self):
        """
        Creates and assigns 'SendMessage' tools to each agent based on the agency's structure.

        This method iterates through the agents and threads in the agency, creating SendMessage tools for each agent. These tools enable agents to send messages to other agents as defined in the agency's structure. The SendMessage tools are tailored to the specific recipient agents that each agent can communicate with.

        No input parameters.

        No output parameters; this method modifies the agents' toolset internally.
        """
        for agent_name, threads in self.agents_and_threads.items():
            recipient_names = list(threads.keys())
            recipient_agents = self.get_agents_by_names(recipient_names)
            agent = self.get_agent_by_name(agent_name)
            agent.add_tool(self._create_send_message_tool(agent, recipient_agents))
            if self.async_mode:
                agent.add_tool(self._create_get_response_tool(agent, recipient_agents))

    def _create_send_message_tool(self, agent: Agent, recipient_agents: List[Agent]):
        """
        Creates a SendMessage tool to enable an agent to send messages to specified recipient agents.


        Parameters:
        agent (Agent): The agent who will be sending messages.
        recipient_agents (List[Agent]): A list of recipient agents who can receive messages.

        Returns:
        SendMessage: A SendMessage tool class that is dynamically created and configured for the given agent and its recipient agents. This tool allows the agent to send messages to the specified recipients, facilitating inter-agent communication within the agency.
        """
        recipient_names = [agent.name for agent in recipient_agents]
        recipients = Enum("recipient", {name: name for name in recipient_names})

        agent_descriptions = ""
        for recipient_agent in recipient_agents:
            if not recipient_agent.description:
                continue
            agent_descriptions += recipient_agent.name + ": "
            agent_descriptions += recipient_agent.description + "\n"

        outer_self = self

        class SendMessage(BaseTool):
            instructions: str = Field(...,
                                      description="Please repeat your instructions step-by-step, including both completed "
                                                  "and the following next steps that you need to perfrom. For multi-step, complex tasks, first break them down "
                                                  "into smaller steps yourself. Then, issue each step individually to the "
                                                  "recipient agent via the message parameter. Each identified step should be "
                                                  "sent in separate message.")
            recipient: recipients = Field(..., description=agent_descriptions)
            message: str = Field(...,
                                 description="Specify the task required for the recipient agent to complete. Focus on "
                                             "clarifying what the task entails, rather than providing exact "
                                             "instructions.")
            message_files: List[str] = Field(default=None,
                                             description="A list of file ids to be sent as attachments to this message. Only use this if you have the file id that starts with 'file-'.",
                                             examples=["file-1234", "file-5678"])
            caller_agent_name: str = Field(default=agent.name,
                                           description="The agent calling this tool. Defaults to your name. Do not change it.")

            @field_validator('recipient')
            def check_recipient(cls, value):
                if value.value not in recipient_names:
                    raise ValueError(f"Recipient {value} is not valid. Valid recipients are: {recipient_names}")
                return value

            @field_validator('caller_agent_name')
            def check_caller_agent_name(cls, value):
                if value != agent.name:
                    raise ValueError(f"Caller agent name must be {agent.name}.")
                return value

            def run(self):
                thread = outer_self.agents_and_threads[self.caller_agent_name][self.recipient.value]

                if not outer_self.async_mode:
                    gen = thread.get_completion(message=self.message, message_files=self.message_files)
                    try:
                        while True:
                            yield next(gen)
                    except StopIteration as e:
                        message = e.value
                else:
                    message = thread.get_completion_async(message=self.message, message_files=self.message_files)

                return message or ""

        SendMessage.caller_agent = agent
        if self.async_mode:
            SendMessage.__doc__ = self.send_message_tool_description_async
        else:
            SendMessage.__doc__ = self.send_message_tool_description

        return SendMessage

    def _create_get_response_tool(self, agent: Agent, recipient_agents: List[Agent]):
        """
        Creates a CheckStatus tool to enable an agent to check the status of a task with a specified recipient agent.
        """
        recipient_names = [agent.name for agent in recipient_agents]
        recipients = Enum("recipient", {name: name for name in recipient_names})

        outer_self = self

        class GetResponse(BaseTool):
            """This tool allows you to check the status of a task or get a response from a specified recipient agent, if the task has been completed. You must always use 'SendMessage' tool with the designated agent first."""
            recipient: recipients = Field(...,
                                          description=f"Recipient agent that you want to check the status of. Valid recipients are: {recipient_names}")
            caller_agent_name: str = Field(default=agent.name,
                                           description="The agent calling this tool. Defaults to your name. Do not change it.")

            @field_validator('recipient')
            def check_recipient(cls, value):
                if value.value not in recipient_names:
                    raise ValueError(f"Recipient {value} is not valid. Valid recipients are: {recipient_names}")
                return value

            @field_validator('caller_agent_name')
            def check_caller_agent_name(cls, value):
                if value != agent.name:
                    raise ValueError(f"Caller agent name must be {agent.name}.")
                return value

            def run(self):
                thread = outer_self.agents_and_threads[self.caller_agent_name][self.recipient.value]

                return thread.check_status()

        GetResponse.caller_agent = agent

        return GetResponse

    def get_agent_by_name(self, agent_name):
        """
        Retrieves an agent from the agency based on the agent's name.

        Parameters:
        agent_name (str): The name of the agent to be retrieved.

        Returns:
        Agent: The agent object with the specified name.

        Raises:
        Exception: If no agent with the given name is found in the agency.
        """
        for agent in self.agents:
            if agent.name == agent_name:
                return agent
        raise Exception(f"Agent {agent_name} not found.")

    def get_agents_by_names(self, agent_names):
        """
        Retrieves a list of agent objects based on their names.

        Parameters:
        agent_names: A list of strings representing the names of the agents to be retrieved.

        Returns:
        A list of Agent objects corresponding to the given names.
        """
        return [self.get_agent_by_name(agent_name) for agent_name in agent_names]

    def get_agent_ids(self):
        """
        Retrieves the IDs of all agents currently in the agency.

        Returns:
        List[str]: A list containing the unique IDs of all agents.
        """
        return [agent.id for agent in self.agents]

    def get_agent_names(self):
        """
        Retrieves the names of all agents in the agency.

        Parameters:
        None

        Returns:
        List[str]: A list of names of all agents currently part of the agency.
        """
        return [agent.name for agent in self.agents]

    def get_recipient_names(self):
        """
        Retrieves the names of all agents in the agency.

        Returns:
        A list of strings, where each string is the name of an agent in the agency.
        """
        return [agent.name for agent in self.agents]

    def get_class_folder_path(self):
        """
        Retrieves the absolute path of the directory containing the class file.

        Returns:
        str: The absolute path of the directory where the class file is located.
        """
        return os.path.abspath(os.path.dirname(inspect.getfile(self.__class__)))

import inspect
import os
import uuid
from enum import Enum
from typing import List

from pydantic import Field, field_validator
from rich.console import Console

from agency_swarm.agents import Agent
from agency_swarm.threads import Thread
from agency_swarm.tools import BaseTool
from agency_swarm.user import User

console = Console()


class Agency:

    def __init__(self, agency_chart, shared_instructions=""):
        """
        Initializes the Agency object, setting up agents, threads, and core functionalities.

        Parameters:
        agency_chart: The structure defining the hierarchy and interaction of agents within the agency.
        shared_instructions (str, optional): A path to a file containing shared instructions for all agents. Defaults to an empty string.

        This constructor initializes various components of the Agency, including CEO, agents, threads, and user interactions. It parses the agency chart to set up the organizational structure and initializes the messaging tools, agents, and threads necessary for the operation of the agency. Additionally, it prepares a main thread for user interactions.
        """
        self.ceo = None
        self.agents = []
        self.agents_and_threads = {}

        if os.path.isfile(os.path.join(self.get_class_folder_path(), shared_instructions)):
            self._read_instructions(os.path.join(self.get_class_folder_path(), shared_instructions))
        elif os.path.isfile(shared_instructions):
            self._read_instructions(shared_instructions)
        else:
            self.shared_instructions = shared_instructions

        self._parse_agency_chart(agency_chart)
        self._create_send_message_tools()
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
        gen = self.main_thread.get_completion(message=message, message_files=message_files, yield_messages=yield_messages)

        if not yield_messages:
            while True:
                try:
                    next(gen)
                except StopIteration as e:
                    return e.value

        return gen

    def demo_gradio(self, height=600):
        """
        Launches a Gradio-based demo interface for the agency chatbot.

        Parameters:
        height (int, optional): The height of the chatbot widget in the Gradio interface. Default is 600.

        This method sets up and runs a Gradio interface, allowing users to interact with the agency's chatbot. It includes a text input for the user's messages and a chatbot interface for displaying the conversation. The method handles user input and chatbot responses, updating the interface dynamically.
        """
        try:
            import gradio as gr
        except ImportError:
            raise Exception("Please install gradio: pip install gradio")

        with gr.Blocks() as demo:
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
        demo.launch()
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

    def plot_agency_chart(self):
        pass

    def _create_send_message_tools(self):
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
            """Use this tool to facilitate direct, synchronous communication between specialized agents within your agency. When you send a message using this tool, you receive a response exclusively from the designated recipient agent. To continue the dialogue, invoke this tool again with the desired recipient and your follow-up message. Remember, communication here is synchronous; the recipient agent won't perform any tasks post-response. You are responsible for relaying the recipient agent's responses back to the user, as they do not have direct access to these replies. Keep engaging with the tool for continuous interaction until the task is fully resolved."""
            chain_of_thought: str = Field(...,
                                          description="Think step by step to determine the correct recipient and "
                                                      "message. For multi-step tasks, first break it down into smaller"
                                                      "steps. Then, determine the recipient and message for each step.")
            recipient: recipients = Field(..., description=agent_descriptions)
            message: str = Field(...,
                                 description="Specify the task required for the recipient agent to complete. Focus on "
                                             "clarifying what the task entails, rather than providing exact "
                                             "instructions.")
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

                gen = thread.get_completion(message=self.message)
                try:
                    while True:
                        yield next(gen)
                except StopIteration as e:
                    message = e.value

                return message or ""

        return SendMessage

    def get_recipient_names(self):
        """
        Retrieves the names of all agents in the agency.

        Returns:
        A list of strings, where each string is the name of an agent in the agency.
        """
        return [agent.name for agent in self.agents]

    def _init_agents(self):
        """
        Initializes all agents in the agency with unique IDs, shared instructions, and OpenAI models.

        This method iterates through each agent in the agency, assigns a unique ID, adds shared instructions, and initializes the OpenAI models for each agent.

        There are no input parameters.

        There are no output parameters as this method is used for internal initialization purposes within the Agency class.
        """
        for agent in self.agents:
            if "temp_id" in agent.id:
                agent.id = None
            agent.add_shared_instructions(self.shared_instructions)
            agent.init_oai()

    def _init_threads(self):
        """
        Initializes threads for communication between agents within the agency.

        This method creates Thread objects for each pair of interacting agents as defined in the agents_and_threads attribute of the Agency. Each thread facilitates communication and task execution between an agent and its designated recipient agent.

        No input parameters.

        Output Parameters:
        This method does not return any value but updates the agents_and_threads attribute with initialized Thread objects.
        """
        for agent_name, threads in self.agents_and_threads.items():
            for other_agent, items in threads.items():
                self.agents_and_threads[agent_name][other_agent] = Thread(self.get_agent_by_name(items["agent"]),
                                                                          self.get_agent_by_name(
                                                                              items["recipient_agent"]))

    def get_class_folder_path(self):
        """
        Retrieves the absolute path of the directory containing the class file.

        Returns:
        str: The absolute path of the directory where the class file is located.
        """
        return os.path.abspath(os.path.dirname(inspect.getfile(self.__class__)))

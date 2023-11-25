import inspect
import os
import uuid
from enum import Enum
from typing import List

from pydantic import Field, field_validator

from agency_swarm.agents import Agent
from agency_swarm.threads import Thread
from agency_swarm.tools import BaseTool
from agency_swarm.user import User


class Agency:

    def __init__(self, agency_chart, shared_instructions=""):
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

    def get_completion(self, message: str, yield_messages=True):
        return self.main_thread.get_completion(message=message, yield_messages=yield_messages)

    def demo_gradio(self, height=600):
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

    def run_demo(self):
        while True:
            text = input("USER: ")

            try:
                gen = self.main_thread.get_completion(message=text)
                while True:
                    message = next(gen)
                    message.cprint()
            except StopIteration as e:
                pass

    def _parse_agency_chart(self, agency_chart):
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
        for agent in self.agents:
            if agent.name == agent_name:
                return agent
        raise Exception(f"Agent {agent_name} not found.")

    def get_agents_by_names(self, agent_names):
        return [self.get_agent_by_name(agent_name) for agent_name in agent_names]

    def get_agent_ids(self):
        return [agent.id for agent in self.agents]

    def get_agent_names(self):
        return [agent.name for agent in self.agents]

    def _read_instructions(self, path):
        path = path
        with open(path, 'r') as f:
            self.shared_instructions = f.read()

    def plot_agency_chart(self):
        pass

    def _create_send_message_tools(self):
        for agent_name, threads in self.agents_and_threads.items():
            recipient_names = list(threads.keys())
            recipient_agents = self.get_agents_by_names(recipient_names)
            agent = self.get_agent_by_name(agent_name)
            agent.add_tool(self._create_send_message_tool(agent, recipient_agents))

    def _create_send_message_tool(self, agent: Agent, recipient_agents: List[Agent]):
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
                                                      "message.")
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
        # This method should return the current list of valid recipient names
        return [agent.name for agent in self.agents]

    def _init_agents(self):
        for agent in self.agents:
            agent.id = None
            agent.add_instructions(self.shared_instructions)
            agent.init_oai()

    def _init_threads(self):
        for agent_name, threads in self.agents_and_threads.items():
            for other_agent, items in threads.items():
                self.agents_and_threads[agent_name][other_agent] = Thread(self.get_agent_by_name(items["agent"]),
                                                                          self.get_agent_by_name(
                                                                              items["recipient_agent"]))

    def get_class_folder_path(self):
        return os.path.abspath(os.path.dirname(inspect.getfile(self.__class__)))

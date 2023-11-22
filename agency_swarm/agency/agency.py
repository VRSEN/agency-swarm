from typing import List, Literal, Optional

from pydantic import Field

from agency_swarm.agents import BaseAgent
from agency_swarm.threads import Thread
from agency_swarm.tools import BaseTool
from agency_swarm.user import User
import uuid


class Agency:

    def __init__(self, agency_chart, manifesto=""):
        self.ceo = None
        self.agents = []
        self.agents_and_threads = {}

        self._parse_agency_chart(agency_chart)
        self._create_send_message_tools()
        self._init_agents()
        self._init_threads()

        self.manifesto = manifesto

        self.user = User()
        self.main_thread = Thread(self.user, self.ceo)

    def yield_completion(self, message: str):
        return self.main_thread.get_completion(message=message)

    def run_demo(self):
        while True:
            text = input("USER: ")

            for message in self.main_thread.get_completion(message=text):
                message.cprint()

    def _parse_agency_chart(self, agency_chart):
        for node in agency_chart:
            if isinstance(node, BaseAgent):
                if self.ceo:
                    raise Exception("Only 1 ceo is supported for now.")
                self.ceo = node
                self._add_agent(self.ceo)

            elif isinstance(node, list):
                for i, agent in enumerate(node):
                    if not isinstance(agent, BaseAgent):
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

    def plot_agency_chart(self):
        pass

    def _create_send_message_tools(self):
        print("agent1 tools", self.agents[1].tools)
        for agent_name, threads in self.agents_and_threads.items():
            recipient_names = list(threads.keys())
            print("recipient_names", recipient_names)
            recipient_agents = self.get_agents_by_names(recipient_names)
            agent = self.get_agent_by_name(agent_name)
            agent.add_tool(self._create_send_message_tool(agent, recipient_agents))
            print("Added send message tool to ", agent.name)
        print("agent1 tools", self.agents[1].tools)

    def _create_send_message_tool(self, agent: BaseAgent, recipient_agents: List[BaseAgent]):
        recipients: List[str] = [agent.name for agent in recipient_agents]

        agent_descriptions = ""
        for recipient_agent in recipient_agents:
            if not recipient_agent.description:
                continue
            agent_descriptions += recipient_agent.name + ": "
            agent_descriptions += recipient_agent.description + "\n"

        outer_self = self

        class SendMessage(BaseTool):
            """Send messages to other specialized agents in this group chat."""
            chain_of_thought: str = Field(...,
                                          description="Think step by step to determine the correct recipient and "
                                                      "message.")
            recipient: Literal[*recipients] = Field(..., description=agent_descriptions)
            message: str = Field(...,
                                 description="Specify the task required for the recipient agent to complete. Focus on "
                                             "clarifying what the task entails, rather than providing exact "
                                             "instructions.")
            caller_agent_name: Literal[agent.name] = Field(agent.name,
                                                           description="The agent calling this tool. Defaults to your name. Do not change it.")

            def run(self):
                thread = outer_self.agents_and_threads[self.caller_agent_name][self.recipient]

                message = thread.get_completion(message=self.message)

                return message

        return SendMessage

    def _init_agents(self):
        for agent in self.agents:
            agent.id = None
            agent.init_assistant()

    def _init_threads(self):
        for agent_name, threads in self.agents_and_threads.items():
            for other_agent, items in threads.items():
                self.agents_and_threads[agent_name][other_agent] = Thread(self.get_agent_by_name(items["agent"]),
                                                                          self.get_agent_by_name(
                                                                              items["recipient_agent"]))

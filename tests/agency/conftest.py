import pytest
import tempfile

from dotenv import load_dotenv, find_dotenv

from agency_swarm import Agent, Agency, BaseTool
from enum import Enum
from agency_swarm.agency.async_agency import AsyncAgency
from agency_swarm import set_openai_key
import os

from agency_swarm.agents.async_agent import AsyncAgent
from agency_swarm.tools.async_base_tool import AsyncBaseTool

load_dotenv(find_dotenv())
set_openai_key(os.getenv("OPENAI_API_KEY"))


class UselessTool(BaseTool):
    """
    This tool is useless and does nothing.
    """

    def run(self):
        response = {"ok": True}
        return "successfully did nothing" if response["ok"] else f"message not sent: response was {response}"


class AsyncUselessTool(AsyncBaseTool):
    """
    This async tool is useless and does nothing.
    """

    async def run(self):
        response = {"ok": True}
        return "successfully did nothing" if response["ok"] else f"message not sent: response was {response}"


class Agents(Enum):
    Aria = Agent(name="Aria",
                 description="Responsible for client communication, task planning and management. Aria is responsible for commnicating with the User through Slack, and seeking for actions that carry significant or substantial consequences, while actions with trivial or inconsequential outcomes  be approved by herself.",
                 instructions="You must converse with other agents to ensure complete task execution.",
                 # can be a file like ./instructions.md
                 files_folder=tempfile.mkdtemp(),
                 tools=[UselessTool])
    Burt = Agent(name="Burt",
                 description="cynical, critical lazy agent most likely to find a reason not to do the work, Burt tries to find a reason that work shouldnt be completed.",
                 instructions="You always try to find a reason NOT to do what is instructed from you.",
                 # can be a file like ./instructions.md
                 files_folder=tempfile.mkdtemp(),
                 tools=[UselessTool])


class AsyncAgents(Enum):
    Aria = AsyncAgent(name="Aria",

                      description="Responsible for client communication, task planning and management. Aria is responsible for commnicating with the User through Slack, and seeking for actions that carry significant or substantial consequences, while actions with trivial or inconsequential outcomes  be approved by herself.",
                      instructions="You must converse with other agents to ensure complete task execution.",
                      # can be a file like ./instructions.md
                      files_folder=tempfile.mkdtemp(),
                      tools=[AsyncUselessTool])
    Burt = AsyncAgent(name="Burt",

                      description="cynical, critical lazy agent most likely to find a reason not to do the work, Burt tries to find a reason that work shouldnt be completed.",
                      instructions="You always try to find a reason NOT to do what is instructed from you.",
                      # can be a file like ./instructions.md
                      files_folder=tempfile.mkdtemp(),
                      tools=[AsyncUselessTool])


@pytest.fixture
def agency_chart():
    return [Agents.Aria.value,  # CEO will be the entry point for communication with the user
            [Agents.Aria.value, Agents.Burt.value]]  # CEO can initiate communication with Developer]



@pytest.fixture
def async_agency_chart():
    return [AsyncAgents.Aria.value,  # CEO will be the entry point for communication with the user
            [AsyncAgents.Aria.value, AsyncAgents.Burt.value]]


@pytest.fixture
def agency(agency_chart, shared_instructions):
    return Agency(agency_chart, shared_instructions)


@pytest.fixture
def async_agency(async_agency_chart, shared_instructions):
    agency = AsyncAgency(async_agency_chart, shared_instructions)
    return agency





@pytest.fixture
def shared_instructions():
    return """you are a legal agency , 
              you conduct feasibiluy research including assessing the merit of a case, 
              and drafting skeleton arguments in accordance with the UK Legal System"""

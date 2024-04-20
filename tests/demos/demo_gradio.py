import sys

import gradio as gr

sys.path.insert(0, './agency-swarm')

from agency_swarm import set_openai_key, Agent

from agency_swarm.agency.agency import Agency
from agency_swarm.tools.oai import FileSearch

ceo = Agent(name="CEO",
            description="Responsible for client communication, task planning and management.",
            instructions="Analyze uploaded files with myfiles_browser tool.", # can be a file like ./instructions.md
            tools=[FileSearch])


test_agent = Agent(name="Test Agent1",
                     description="Responsible for testing.",
                     instructions="Read files with myfiles_browser tool.", # can be a file like ./instructions.md
                     tools=[FileSearch])

test_agent2 = Agent(name="Test Agent2",
                     description="Responsible for testing.",
                     instructions="Read files with myfiles_browser tool.", # can be a file like ./instructions.md
                     tools=[FileSearch])



agency = Agency([
    ceo, test_agent, test_agent2
], shared_instructions="")

# agency.demo_gradio()

print(agency.get_completion("Hello", recipient_agent=test_agent, yield_messages=False))


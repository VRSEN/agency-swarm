import sys

import gradio as gr

from agency_swarm import set_openai_key, Agent

sys.path.insert(0, '../agency-swarm')

from agency_swarm.agency.agency import Agency
from agency_swarm.tools.oai import Retrieval

ceo = Agent(name="CEO",
            description="Responsible for client communication, task planning and management.",
            instructions="Read files with myfiles_browser tool.", # can be a file like ./instructions.md
            tools=[Retrieval])



agency = Agency([
    ceo,
], shared_instructions="")


agency.demo_gradio(height=900)


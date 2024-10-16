import sys

import gradio as gr

sys.path.insert(0, './agency-swarm')

from agency_swarm import set_openai_key, Agent

from agency_swarm.agency.agency import Agency
from agency_swarm.tools.oai import FileSearch, CodeInterpreter
from agency_swarm.tools.BaseTool import BaseTool

class PrintTool(BaseTool):
    def run(self, **kwargs):
        print("This is a test tool from BaseTool.")
        return "Printed successfully."

class AnotherPrintTool(BaseTool):
    def run(self, **kwargs):
        print("This is another test tool from BaseTool.")
        return "Another print successful."

ceo = Agent(name="CEO",
            description="Responsible for client communication, task planning and management.",
            instructions="Analyze uploaded files with myfiles_browser tool.", # can be a file like ./instructions.md
            tools=[FileSearch, CodeInterpreter, PrintTool, AnotherPrintTool], 
            file_search={'max_num_results': 50})


test_agent = Agent(name="Test Agent1",
                     description="Responsible for testing.",
                     instructions="Read files with myfiles_browser tool.", # can be a file like ./instructions.md
                     tools=[FileSearch])

test_agent2 = Agent(name="Test Agent2",
                     description="Responsible for testing.",
                     instructions="Read files with myfiles_browser tool.", # can be a file like ./instructions.md
                     tools=[FileSearch])



agency = Agency([
    ceo, [ceo, test_agent, test_agent2],
], shared_instructions="", settings_path="./test_settings.json")

# agency.demo_gradio()

print(agency.get_completion("Use 2 print tools", yield_messages=False))


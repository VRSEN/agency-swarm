from agency_swarm import Agent
from LangGraph_test.example_tool import RepeateMessage

_name = "repeater"

_description = """
Responsible for repeating message.
"""

_instruction = """
你接受到message时，调用RepeateMessage来重复这个message，你必须向RepeateMessage提供你要重复的message
"""

_tools = [RepeateMessage]

_file_folder = ""

def create_agent(*, 
                 description=_description, 
                 instuction=_instruction, 
                 tools=_tools, 
                 files_folder=_file_folder):
    return Agent(name=_name,
                 tools=tools,
                 description=description,
                 instructions=instuction,
                 files_folder=_file_folder,
                 temperature=0.5,
                 response_format='auto',
                 max_prompt_tokens=25000,)
from agency_swarm import Agent
from LangGraph_test.example_tool import RepeateMessage

_name = "palindromist"

_description = """
Responsible for writing a palindrome
"""

_instruction = """
你接受到message时，输出它的回文
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
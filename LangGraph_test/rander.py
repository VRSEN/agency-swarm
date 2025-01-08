from agency_swarm import Agent
from LangGraph_test.example_tool import RepeateMessage

_name = "rander"

_description = """
Responsible for generate a random number.
"""

_instruction = """
随便给出一个[0, 10]之间的数字，附加在用户输入之后，并输出
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
from agency_swarm import Agent
from agents.basic_agents.jobs_agent.tools import Sleep
from agents.basic_agents.jobs_agent.tools import ReadFile

_name = "jobs_agent"

_description = """
jobs_agent负责查询任务执行状态。
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = current_path + "/instructions.md"

_tools = [Sleep.Sleep, ReadFile.ReadFile]

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
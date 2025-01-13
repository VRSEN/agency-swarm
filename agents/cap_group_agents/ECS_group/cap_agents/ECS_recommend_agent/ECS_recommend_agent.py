from agency_swarm import Agent
from agents.cap_group_agents.ECS_group.cap_agents.ECS_recommend_agent.tools import (
    ReadAPI
)

_name = "ECS_recommend_agent"

_description = """
负责华为云ECS规格推荐任务，包括：地域推荐。
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = current_path + "/instructions.md"

_tools = [ReadAPI.ReadAPI]

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
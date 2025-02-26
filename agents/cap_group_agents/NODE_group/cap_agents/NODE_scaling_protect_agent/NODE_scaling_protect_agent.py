from agency_swarm import Agent
from agents.cap_group_agents.NODE_group.cap_agents.NODE_scaling_protect_agent.tools import (ReadAPI)
from agents.cap_group_agents.cap_agent_instruction import cap_agent_instruction

_name = "NODE_scaling_protect_agent"
_manager_name = "NODE_manager"
_description = """
负责k8s集群节点缩容保护任务，包括：节点开启缩容保护，节点关闭缩容保护。
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = cap_agent_instruction(_name, _description, _manager_name)

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
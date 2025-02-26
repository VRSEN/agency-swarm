from agency_swarm import Agent
from agents.cap_group_agents.CLUSTER_group.cap_agents.CLUSTER_specification_change_agent.tools import (ReadAPI)
from agents.cap_group_agents.cap_agent_instruction import cap_agent_instruction

_name = "CLUSTER_specification_change_agent"
_manager_name = "CLUSTER_manager"
_description = """
负责k8s集群规格变更任务，包括：变更集群规格。
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
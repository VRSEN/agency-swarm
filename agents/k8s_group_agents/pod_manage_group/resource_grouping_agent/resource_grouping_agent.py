from agency_swarm import Agent

from agents.k8s_group_agents.k8s_agent_instruction import k8s_agent_instruction
from agents.k8s_group_agents.tools.ExecuteCommand import ExecuteCommand
from agents.k8s_group_agents.tools.WriteFile import WriteFile

_name = "resource_grouping_agent"
_description = """
负责k8s集群的pod资源分组任务，包括：1.Label管理。例如，按标签查询，为Pod分配合理的Label；2.Namespace管理。例如，创建、查询、删除Namespace，为Pod分配Namespace。
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = k8s_agent_instruction(_name,_description)

_tools = [ExecuteCommand, WriteFile]

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
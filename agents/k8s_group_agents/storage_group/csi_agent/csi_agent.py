from agency_swarm import Agent

from agents.k8s_group_agents.k8s_agent_instruction import k8s_agent_instruction
from agents.k8s_group_agents.tools.ExecuteCommand import ExecuteCommand
from agents.k8s_group_agents.tools.WriteFile import WriteFile

_name = "csi_agent"
_description = """
负责CSI的管理，包括各种CSI插件、CSI相关资源、适配存储类型。
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
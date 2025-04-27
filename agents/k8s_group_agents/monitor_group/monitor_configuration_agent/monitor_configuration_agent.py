from agency_swarm import Agent
from agents.k8s_group_agents.k8s_agent_instruction import k8s_agent_instruction
from agents.k8s_group_agents.tools.ExecuteCommand import ExecuteCommand

_name = "monitor_configuration_agent"

_manager_name = "monitor_manager"

_description = """
负责修改k8s集群的插件或配置文件。
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = k8s_agent_instruction(_name, _description, _manager_name)

_tools = [ExecuteCommand]

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
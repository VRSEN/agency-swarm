from agency_swarm import Agent

from agents.k8s_group_agents.k8s_agent_instruction import k8s_agent_instruction
from agents.k8s_group_agents.tools.ExecuteCommand import ExecuteCommand

_name = "task_manage_agent"
_description = """
负责k8s集群的pod的任务管理，包括：1.普通任务创建；2.CronJob创建，例如定时设置
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = k8s_agent_instruction(_name,_description)

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
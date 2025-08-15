from agency_swarm import Agent
from agents.k8s_group_agents.tools.ExecuteCommand import ExecuteCommand
from agents.k8s_group_agents.vm_agent_instruction import vm_agent_instruction

from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile


_name = "kubeadm_agent"
_description = """
负责使用kubeadm与k8s集群进行交互
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = vm_agent_instruction(_name,_description)

_tools = [ReadJsonFile,ExecuteCommand]

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
                 files_folder=files_folder,
                 temperature=0.5,
                 response_format='auto',
                 max_prompt_tokens=25000,)
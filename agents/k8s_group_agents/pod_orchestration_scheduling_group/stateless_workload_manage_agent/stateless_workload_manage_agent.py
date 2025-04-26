from agency_swarm import Agent

from agents.k8s_group_agents.k8s_agent_instruction import k8s_agent_instruction
from agents.k8s_group_agents.tools.ExecuteCommand import ExecuteCommand

_name = "stateless_workload_manage_agent"
_manager_name = "pod_orchestration_scheduling_manager"
_description = """
负责k8s集群的pod的无状态负载管理任务，包括：1.Deployment创建、查询、删除；2. ReplicaSer查询；3. 升级策略管理，例如RollingUpdate、Recreate等；4.回滚。
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = k8s_agent_instruction(_name,_description,_manager_name)

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
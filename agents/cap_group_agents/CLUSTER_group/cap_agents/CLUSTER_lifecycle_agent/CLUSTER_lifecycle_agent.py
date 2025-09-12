from agency_swarm import Agent
from agents.cap_group_agents.CLUSTER_group.cap_agents.CLUSTER_specification_change_agent.tools import (
    ReadAPI
)
from agents.cap_group_agents.cap_agent_instruction import cap_agent_instruction
from agents.basic_agents.job_agent.tools.CallAPI import CallAPI
from agents.cap_group_agents.CLUSTER_group.tools import (
    GetEndPointAndProjectID, AskManagerParams
)

_name = "CLUSTER_lifecycle_agent"
_manager_name = "CLUSTER_manager"
_description = """
负责k8s集群生命周期管理任务，包括：创建集群，删除集群，更新指定的集群，获取指定的集群，集群休眠，集群唤醒，查询指定集群支持配置的参数列表，批量添加指定集群的资源标签，批量删除指定集群的资源标签。
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = cap_agent_instruction(_name, _description, _manager_name)

_tools = [ReadAPI.ReadAPI, CallAPI, GetEndPointAndProjectID.GetEndPointAndProjectID, AskManagerParams.AskManagerParams]

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
from agency_swarm import Agent
from agents.cap_group_agents.NODE_group.cap_agents.NODE_pool_agent.tools import (
    ReadAPI, GetEndPointAndProjectID
)
from agents.cap_group_agents.cap_agent_instruction import cap_agent_instruction
from agents.basic_agents.job_agent.tools.CallAPI import CallAPI

_name = "NODE_pool_agent"
_manager_name = "NODE_manager"
_description = """
负责k8s集群节点池管理任务，包括：创建节点池，获取指定的节点池，获取集群下所有节点池，更新指定节点池，删除节点池，查询指定节点池支持配置的参数列表，查询指定节点池支持配置的参数内容，修改指定节点池配置参数的值，伸缩节点池，同步节点池。
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = cap_agent_instruction(_name, _description, _manager_name)

_tools = [ReadAPI.ReadAPI, CallAPI, GetEndPointAndProjectID.GetEndPointAndProjectID]

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
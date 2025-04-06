from agency_swarm import Agent
from agents.cap_group_agents.NODE_group.cap_agents.NODE_lifecycle_agent.tools import (
    ReadAPI, GetEndPointAndProjectID
)
from agents.cap_group_agents.cap_agent_instruction import cap_agent_instruction
from agents.basic_agents.job_agent.tools.CallAPI import CallAPI

_name = "NODE_lifecycle_agent"
_manager_name = "NODE_manager"
_description = """
负责k8s集群节点生命周期管理任务，包括：创建节点，获取指定的节点，获取集群下所有节点，更新指定的节点，删除节点，纳管节点，重置节点，同步节点，批量同步节点。
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
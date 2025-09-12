from agency_swarm import Agent
from agents.cap_group_agents.EVS_group.cap_agents.EVS_clouddiskt_agent.tools import (
    ReadAPI
)
from agents.cap_group_agents.cap_agent_instruction import cap_agent_instruction
from agents.basic_agents.job_agent.tools.CallAPI import CallAPI
from agents.cap_group_agents.EVS_group.tools import (
    GetEndPointAndProjectID, AskManagerParams   
)

_name = "EVS_clouddiskt_agent"
_manager_name = "EVS_manager"
_description = """
负责华为云云硬盘管理任务，包括：创建云硬盘、更新云硬盘、查询所有云硬盘详情、查询单个云硬盘详情、扩容云硬盘、删除云硬盘。
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = cap_agent_instruction(_name,_description,_manager_name)

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
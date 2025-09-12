from agency_swarm import Agent
from agents.cap_group_agents.IMS_group.cap_agents.IMS_agent.tools import (
    ReadAPI, GetEndPointAndProjectID, AskManagerParams
)

from agents.cap_group_agents.cap_agent_instruction import cap_agent_instruction
from agents.basic_agents.job_agent.tools.CallAPI import CallAPI

_name = "IMS_agent"

_manager_name = "IMS_manager"

_description = """
负责华为云镜像资源管理任务，包括：查询镜像列表，更新镜像信息，制作镜像，镜像文件快速导入，使用外部镜像文件制作数据镜像，制作整机镜像，注册镜像，导出镜像，查询镜像支持的OS列表。
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
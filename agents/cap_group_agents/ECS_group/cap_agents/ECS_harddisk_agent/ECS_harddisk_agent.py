from agency_swarm import Agent
from agents.cap_group_agents.ECS_group.cap_agents.ECS_harddisk_agent.tools import (
    ReadLog, WriteLog
)

_name = "ECS_harddisk_agent"

_description = """
负责华为云ECS硬盘管理任务，包括：查询弹性云服务器单个磁盘信息、查询弹性云服务器挂载磁盘列表信息，查询弹性云服务器挂载磁盘列表详情信息，弹性云服务器挂载磁盘、弹性云服务器卸载磁盘，修改弹性云服务器挂载的单个磁盘信息。
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = current_path + "/instructions.md"

_tools = [ReadLog.ReadLog, WriteLog.WriteLog]

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
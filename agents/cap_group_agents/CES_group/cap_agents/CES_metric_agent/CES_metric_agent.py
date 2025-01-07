from agency_swarm import Agent
from agents.cap_group_agents.CES_group.cap_agents.CES_metric_agent.tools import (
    ReadLog, WriteLog
)

_name = "CES_metric_agent"

_description = """
负责华为云的监控指标管理任务，包括：查询指标列表、查询主机监控维度指标信息。
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = current_path + "/instructions.md"

_tools = [ReadLog, WriteLog]

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
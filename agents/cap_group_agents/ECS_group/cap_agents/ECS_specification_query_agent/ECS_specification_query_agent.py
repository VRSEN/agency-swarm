from agency_swarm import Agent
from agents.cap_group_agents.ECS_group.cap_agents.ECS_specification_query_agent.tools import (
    ReadAPI, GetEndPointAndProjectID
)
from agents.cap_group_agents.cap_agent_instruction import cap_agent_instruction
from agents.basic_agents.job_agent.tools.CallAPI import CallAPI

_name = "ECS_specification_query_agent"
_manager_name = "ECS_manager"
_description = """
负责华为云ECS规格信息查询任务，包括：查询规格详情和规格扩展信息列表，查询规格销售策略， 查询云服务器规格变更支持列表。
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
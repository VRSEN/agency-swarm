from agency_swarm import Agent
from agents.cap_group_agents.VPC_network.cap_agents.VPC_secgroup_agent.tools import (
    ReadAPI
)

_name = "VPC_secgroup_agent"

_description = """
负责华为云安全组管理任务，包括创建安全组、查询安全组、删除安全组，创建安全组规则、查询安全组规则、删除安全组规则。
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = current_path + "/instructions.md"

_tools = [ReadAPI.ReadAPI]

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
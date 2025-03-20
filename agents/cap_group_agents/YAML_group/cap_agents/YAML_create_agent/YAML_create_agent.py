from agency_swarm import Agent
from agents.cap_group_agents.YAML_group.cap_agents.YAML_create_agent.tools import YAML_create
#from agents.cap_group_agents.cap_agent_instruction import cap_agent_instruction

_name = "YAML_create_agent"
_manager_name = "YAML_manager"
_description = """
负责根据用户要求生成可用于k8s系统执行的YAML配置。
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = current_path + "/instructions.md"

_tools = [YAML_create.YAML_create]

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
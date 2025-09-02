from agency_swarm import Agent

from agents.openeuler_agents.openeuler_agent_instruction import openeuler_agent_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
from agents.openeuler_agents.tools.SSHExecuteCommand import SSHExecuteCommand


_name = "permissions_agent"
_description = """
本Agent负责管理OpenEuler系统上的用户权限和文件访问权限，支持以下功能：

1. 修改与用户权限相关的配置文件，例如 /etc/passwd、/etc/group，可实现用户和用户组的权限调整。
2. 使用ACL（Access Control List）命令（如setfacl、getfacl）对指定目录或文件进行访问权限的精细化控制，限制或授权用户的访问权限。

注意事项：
- 仅允许执行与用户权限和文件访问权限相关的操作，禁止执行其他类型的系统命令。
- 修改配置文件前请备份原文件，确保操作安全。
- 所有命令和参数请根据实际需求替换，避免误操作。
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = openeuler_agent_instruction(_name,_description)

_tools = [ReadJsonFile, SSHExecuteCommand]

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
                 files_folder=files_folder,
                 temperature=0.5,
                 response_format='auto',
                 max_prompt_tokens=25000,)
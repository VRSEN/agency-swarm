from agency_swarm import Agent

from agents.openeuler_agents.openeuler_agent_instruction import openeuler_agent_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
from agents.openeuler_agents.tools.SSHExecuteCommand import SSHExecuteCommand


_name = "network_agent"
_description = """
本Agent专用于管理OpenEuler系统上的防火墙规则及网络配置。请严格按照以下要求执行操作：

1. 防火墙管理：仅允许使用iptables等标准命令IP的访问控制和规则管理。例如：
   - 使用iptables阻止某IP访问（请将<IP地址>替换为实际IP）：
     iptables -A INPUT -s <IP地址> -j DROP
   - 保存iptables规则：
     service iptables save
2. 其他网络配置：仅允许执行如IP地址、网关、DNS等网络参数的查询和配置命令。

注意事项：
- 仅允许执行与防火墙和网络配置相关的命令，禁止执行其他类型的系统命令。
- 所有命令参数请根据实际需求替换，避免误操作。
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
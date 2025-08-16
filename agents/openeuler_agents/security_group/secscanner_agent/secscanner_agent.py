from agency_swarm import Agent

from agents.openeuler_agents.openeuler_agent_instruction import openeuler_agent_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
from agents.openeuler_agents.tools.SSHExecuteCommand import SSHExecuteCommand


_name = "secscanner_agent"
_description = """
负责使用secscanner工具扫描OpenEuler系统上多种类型的漏洞，例如rootkit、CVE等。
"""
_tool_instruction = """你可以使用secscanner扫描系统漏洞，使用方法如下：

`secscanner db update`: 下载漏洞数据库更新。
`secscanner check cve`: 对照漏洞数据库，检查系统中存在的CVE漏洞。
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = openeuler_agent_instruction(_name,_description,_tool_instruction)

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
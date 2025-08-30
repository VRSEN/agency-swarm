from agency_swarm import Agent

from agents.openeuler_agents.openeuler_agent_instruction import openeuler_agent_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
from agents.openeuler_agents.tools.SSHExecuteCommand import SSHExecuteCommand


_name = "secscanner_agent"
_description = """
负责使用secscanner工具扫描OpenEuler系统上多种类型的漏洞，例如rootkit、CVE等。
"""
_tool_instruction = """你可以使用secscanner扫描系统漏洞，使用方法如下：
`secscanner check all`: 查询系统综合的安全配置信息
`secscanner db update`: 更新漏洞数据库而非工具本身的更新。
`secscanner check cve`: 对照漏洞数据库，检查系统软件包中存在的CVE漏洞。
`secscanner check basic`: 识别当前系统中基础的安全问题
`secscanner fix basic`: 修复当前系统中基础的安全问题
`secscanner --version`: 通过查看版本的方式确认secscanner工具已经安装情况 
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
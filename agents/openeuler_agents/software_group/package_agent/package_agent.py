from agency_swarm import Agent

from agents.openeuler_agents.openeuler_agent_instruction import openeuler_agent_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
from agents.openeuler_agents.tools.SSHExecuteCommand import SSHExecuteCommand


_name = "package_agent"
_description = """
负责使用yum、rpm等包管理器对软件包进行查询、安装、删除等操作。
具体示例如下
1. 安装rpm包（请将<包名.rpm>替换为实际文件名）：
   rpm -ivh <包名.rpm>
2. 查询已安装的软件包（请将<软件包名>替换为实际名称）：
   yum list installed | grep <软件包名>
3. 卸载软件包（请将<软件包名>替换为实际名称）：
   yum remove <软件包名>
** 注意 **
1. cd命令和其他命令一起执行，使用`&&`连接，例如：`cd repo && rpm -ivh`。
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
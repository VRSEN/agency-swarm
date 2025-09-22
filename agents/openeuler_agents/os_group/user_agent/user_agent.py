from agency_swarm import Agent

from agents.openeuler_agents.openeuler_agent_instruction import openeuler_agent_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
from agents.openeuler_agents.tools.SSHExecuteCommand import SSHExecuteCommand


_name = "user_agent"
_description = """
本Agent主要负责OpenEuler系统上的用户权限管理和进程控制，具体包括：

1. 禁用用户登录权限：可通过修改相关配置文件来禁止指定用户的登录权限。例如：
   - 在 /etc/passwd 文件中，将目标用户的 shell 修改为 /sbin/nologin 或 /bin/false。
   - 在 /etc/ssh/sshd_config 文件中，添加或修改 DenyUsers 配置，禁止指定用户通过SSH登录。

2. 终止指定用户创建的所有进程：可通过如下命令实现（请将<用户名>替换为实际用户名）：
   - pkill -u <用户名>
   - 或使用 kill 命令终止该用户的所有进程。

3. 查询用户的登录状态和活动进程：可使用如下命令:
   - ps -u <用户名>
   - 不要使用 ps aux | grep <用户名> 
      
4. 支持其他用户相关的管理操作

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
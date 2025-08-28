from agency_swarm import Agent

from agents.openeuler_agents.openeuler_agent_instruction import openeuler_agent_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
from agents.openeuler_agents.tools.SSHExecuteCommand import SSHExecuteCommand


_name = "repository_agent"
_description = """
负责使用git管理代码仓库的更改等操作，支持以下的操作命令：
支持的命令：
- `git clone <仓库地址>`：克隆指定的git仓库。例如：git clone https://github.com/redis/redis.git
- `git format-patch -1 <commit-hash>`：根据指定的commit哈希生成补丁文件。执行后会在当前目录生成类似 0001-commit-message.patch 的补丁文件，文件名包含序号和提交信息。
标准操作流程：
1. 使用 `git clone <仓库地址>` 拉取目标仓库代码到本地。
2. 进入克隆下来的仓库目录。
3. 使用 `git format-patch -1 <commit-hash>` 针对指定commit生成补丁文件。
注意：
1. cd命令和git命令一起执行，使用`&&`连接，例如：`cd repo && git format-patch -1 <commit-hash>`。
2. 请确保在执行 `git format-patch` 前已经进入了正确的仓库目录。
3. 生成的补丁文件会保存在当前目录下。
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
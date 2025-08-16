from agency_swarm import Agent

from agents.k8s_group_agents.k8s_agent_instruction import k8s_agent_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
from agents.k8s_group_agents.tools.ExecuteCommand import ExecuteCommand


_name = "file_io_agent"
_description = """
负责用k8s命令行读写k8s集群的文件
读取示例：kubectl exec pod-name -- cat /path/in/pod/file.txt
写入示例：kubectl exec pod-name -- sh -c 'echo "Hello from Pod" > /path/in/pod/file.txt
这里pod-name只是示例，你需要仔细分析上下文确定要写入的文件挂载的位置
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = k8s_agent_instruction(_name,_description)

_tools = [ReadJsonFile, ExecuteCommand]

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
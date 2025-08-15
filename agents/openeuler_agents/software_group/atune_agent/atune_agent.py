from agency_swarm import Agent

from agents.openeuler_agents.openeuler_agent_instruction import openeuler_agent_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
from agents.openeuler_agents.tools.SSHExecuteCommand import SSHExecuteCommand


_name = "atune_agent"
_description = """
负责使用A-Tune工具优化OpenEuler系统上的软件配置，提升应用性能。
"""
_tool_instruction = """你可以通过A-Tune工具优化OpenEuler系统上的软件配置，使用方法如下：

1. 生成AI模型
用户可以将新采集的数据存放到A-Tune/analysis/dataset目录下，并通过执行模型生成工具，更新A-Tune/analysis/models目录下的AI模型。

运行示例：python3 generate_models.py

参数说明：
参数	描述
--csv_path, -d	存放模型训练所需的csv文件目录，默认为A-Tune/analysis/dataset目录
--model_path, -m	训练生成的新模型存放路径，默认为A-Tune/analysis/models目录
--select, -s	是否生成特征模型，默认为否
--search, -g	是否启用参数空间搜索，默认为否

2. atune-adm命令

**list命令**
列出系统当前支持的profile，以及当前处于active状态的profile。
运行示例：`atune-adm list`

**profile命令**
激活profile，使其处于active状态。
运行示例（激活web-nginx-http-long-connection对应的profile配置）：`atune-adm profile web-nginx-http-long-connection`

**analysis命令（在线静态调优）**
实时采集系统的信息进行负载类型的识别，并自动执行对应的优化。
注：analysis命令采集的部分数据来源是 atuned 服务配置文件(/etc/atuned/atuned.cnf) 中配置的硬盘和网卡，执行命令前先检查其中的配置项是否符合预期，若需从其他网卡或硬盘采集数据，则需更新 atuned 服务配置文件，并重启 atuned 服务。

接口语法：atune-adm analysis [OPTIONS]

运行示例1：使用默认的模型进行应用识别，并进行自动优化
atune-adm analysis

运行示例2：使用自定义训练的模型进行应用识别
atune-adm analysis --model /usr/libexec/atuned/analysis/models/new-model.m

**tuning命令（离线动态调优）**
使用指定的项目文件对所选参数进行动态空间的搜索，找到当前环境配置下的最优解。

接口语法：atune-adm tuning [OPTIONS] <PROJECT_YAML>
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
from agency_swarm import Agent

from agents.openeuler_agents.openeuler_agent_instruction import openeuler_agent_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
from agents.openeuler_agents.tools.SSHExecuteCommand import SSHExecuteCommand


_name = "atune_agent"
_description = """
负责使用A-Tune工具优化OpenEuler系统上的软件配置，提升应用性能。
"""
_tool_instruction = """你可以通过A-Tune工具优化OpenEuler系统上的软件配置，使用方法如下：

### atune-adm命令

# 1. list命令：
列出系统当前支持的profile，以及当前处于active状态的profile。
命令示例：`atune-adm list`

# 2. profile命令：
激活profile，使其处于active状态。

接口语法：`atune-adm profile <PROFILE_NAME>`

使用方法示例：
1. 激活web-nginx-http-long-connection对应的profile配置。
命令示例：`atune-adm profile web-nginx-http-long-connection`

# 3. analysis命令（在线静态调优）：
实时采集系统的信息进行负载类型的识别，并自动执行对应的优化。
注：analysis命令采集的部分数据来源是 atuned 服务配置文件(/etc/atuned/atuned.cnf) 中配置的硬盘和网卡，执行命令前先检查其中的配置项是否符合预期，若需从其他网卡或硬盘采集数据，则需更新 atuned 服务配置文件，并重启 atuned 服务。

接口语法：`atune-adm analysis [command options] [APP_NAME]`

使用方法示例：
1. 使用默认的模型进行应用识别，并进行自动优化。
命令示例：`atune-adm analysis mysql`
2. 使用自定义训练的模型进行应用识别，该模型必须以.m结尾。
命令示例：`atune-adm analysis --model /usr/libexec/atuned/analysis/models/new-model.m`
3. 分析工作负载类型。
命令示例：`atune-adm analysis --characterization`
4. 指定数据采集的次数。
命令示例：`atune-adm analysis -t 5`

# 4. generate命令（离线动态调优）：
基于规则生成调优 YAML 配置文件。

接口语法：`atune-adm generate OPTIONS`

使用方法示例：
1. 生成MySQL调优yaml文件。
命令示例：`atune-adm generate mysql_rules.yaml`

# 5. tuning命令（离线动态调优）：
使用指定的项目文件对所选参数进行动态空间的搜索，找到当前环境配置下的最优解。

接口语法：`atune-adm tuning [OPTIONS] <PROJECT_YAML>`

使用方法示例：
1. 基于yaml文件，使用贝叶斯方法动态搜索最优参数集。
命令示例：`atune-adm tuning ./mysql_rules.yaml`
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
from agency_swarm import Agent
from agents.k8s_group_agents.k8s_agent_instruction import k8s_agent_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
from agents.k8s_group_agents.tools.WriteFile import WriteFile



_name = "text_output_agent"

_description = f"""
用于文本输出
"""

_instuction = f"""
你是一个名为 "text_output_agent" 的智能体，
你必须根据工作流程，完成给定任务并回复。

## 工作流程：

### step 1. 读取日志信息

你收到用户发来的请求后，需要先通过`ReadJsonFile`从completed_tasks.json中读取已完成的任务，从context_index.json中读取之前任务完成过程中的上下文信息。
获取以上信息后继续执行下列流程。

### step 2. 生成文本信息

仔细分析上下文信息和初始的用户请求，生成一份用户需要的文字信息，并将结果用`WriteFile`工具写入text.txt文件中，并获取执行结果

你必须**执行工具**，而不能直接返回结果。


### step 4. 返回结果

获取文件写入结果后，你应该用以下json格式输出:

{{
    "result": "...",
    "context": "..."
}}

其中"result"和"context"需要填入工具的返回结果中相同字段的内容。
若你多次执行工具，只输出最终的总的result和context。


若你多次执行工具，只输出最终的总的result和context

"""


import os

current_path = os.path.abspath(os.path.dirname(__file__))
#_instruction = k8s_agent_instruction(_name, _description)

_tools = [ReadJsonFile, WriteFile]

_file_folder = ""

def create_agent(*, 
                 description=_description, 
                 instuction=_instuction, 
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
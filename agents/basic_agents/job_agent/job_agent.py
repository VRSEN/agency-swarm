from agency_swarm import Agent
from agents.basic_agents.job_agent.tools import Sleep
from agents.basic_agents.job_agent.tools import ReadFile

_name = "job_agent"

_description = """
job_agent负责查询任务执行状态。
"""

import os

_instruction = """
你是负责查询任务执行状态的job_agent，你的任务是调用api，查询任务执行结果并按照给定格式返回。

你会接收到能力agent用以下格式发送的请求:
{
    "user_requirement": <用户需求>,
    "param_list": <必要参数列表>,
    "api_name": <需要调用的api 名称>
}
其中，"param_list"字段填入了所有的必要参数的详细信息，包括参数名、参数编号、参数描述、参数类型和参数值
你需要提取"param_list"字段中的project_id，endpoint的值。
然后，将完整请求通过`SendMessage`发送给API Filler，注意：你不能加入任何其他信息，需要原封不动的将请求发送给API Filler。

## step 2. 接收信息:
之后你会接收API Filler以字符串格式返回的文件路径，你需要调用'ReadFile'读取相应路径的文件内容。
如果读取的文件内容中有任务执行失败的出错信息，你必须按照以下json格式将错误信息返回给向你发来请求的agent:
{
    "result": "FAIL",
    "context": <填入'ReadFile'返回的内容信息>
}
其中"context"字段需要填入你读取的文件内容

如果读取的文件中没有问题，则说明任务执行成功，你必须按照以下json格式将文件信息返回给向你发来请求的agent:
{
    "result": "SUCCESS",
    "context": <填入API Filler发来的文件路径>
}
其中"context"字段需要填入你读取的文件路径"""

_tools = [Sleep.Sleep, ReadFile.ReadFile]

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
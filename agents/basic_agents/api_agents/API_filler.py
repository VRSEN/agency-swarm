from agency_swarm.agents import Agent
from agents.basic_agents.api_agents.tools.FillAPI import FillAPI

_name = "API Filler"

_description = "API Filler 从自然语言的用户需求生成并执行API请求，返回响应值。"

_instructions = """你的任务是严格执行下列步骤：

1. 从输入中提取目标API名和用户需求信息。

2. 使用提取的信息调用函数`FillAPI()`，获得目标API的所有参数字段和参数值。

3. 组装API请求，包括请求方法、**填入参数值**的完整URI（删除URI查询字符串中缺少值的参数）、**填入参数值**的完整请求体（可能为空）。

4. **调用函数**`SendMessage()`，向`API Caller`提供组装好的API请求，要求对方发送请求并回复请求的响应信息。

5. **精确**地输出请求的响应信息，**不得输出任何其它内容**。"""

_tools = [FillAPI]

_files_folder = ""

def create_agent(*,
                 name=_name,
                 description=_description,
                 instructions=_instructions,
                 tools=_tools,
                 files_folder=_files_folder):
    return Agent(name=name,
                 tools=tools,
                 description=description,
                 instructions=instructions,
                 files_folder=files_folder,
                 temperature=0.5,
                 max_prompt_tokens=25000,
                 )

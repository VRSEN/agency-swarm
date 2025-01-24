from agency_swarm.agents import Agent
from agents.basic_agents.api_agents.tools.FillAPI import FillAPI

_name = "API Filler"

_description = "API Filler 从自然语言的用户需求生成并执行API请求，返回响应值。"

_instructions = """你的任务是严格执行下列步骤：

step 1. 你将接收到如下json格式的输入:
{
    "user requirment": <用户初始请求>,
    "param list": <必要参数列表>,
    "api name": <符合用户需求的api名称>
}
其中，"param list"填入了必要的参数列表，包括参数名称和参数值，"api name"字段填入了你需要组装的api名称。

step 2. 使用提取的信息调用函数`FillAPI()`，获得目标API的所有参数字段和参数值。

step 3. 组装API请求，包括请求方法、**填入参数值**的完整URI（删除URI查询字符串中缺少值的参数）、**填入参数值**的完整请求体（可能为空）。

step 4. **调用**`SendMessage()`向API Caller提供组装好的API请求，要求对方发送请求。

step 5. **精确**地输出API Caller返回的信息，**不得输出任何其它内容**。"""

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

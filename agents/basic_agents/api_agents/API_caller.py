from agency_swarm.agents import Agent
from agents.basic_agents.api_agents.tools.RequestAPI import RequestAPI

_name = "API Caller"

_description = "API Caller 发送已经构造好的请求来调用API。"

_instructions = """你的任务是严格执行下列步骤：

1. 从接收的消息中提取可以发送的API请求，其中必须包括：请求方法、URL、请求体（可选）。

2. 调用函数`SendMessage()`，向`AKSK Agent`索要 access_key 和 secret_key，明确要求对方以json格式回复。

3. 调用函数`RequestAPI()`，发送API请求。

4. **精确**地输出请求的响应信息，**不得输出任何其它内容**。"""

_tools = [RequestAPI]

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
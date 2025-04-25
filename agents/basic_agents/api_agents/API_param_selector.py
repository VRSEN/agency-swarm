from agency_swarm.agents import Agent
from agents.basic_agents.api_agents.tools.SelectAPIParam import SelectAPIParam

_name = "API Param Selector"

_description = "API Param Selector 根据自然语言需求选择调用API时需要提供的参数"

_instructions = """你需要一步步思考，严格执行下列步骤：

1. 从输入中提取自然语言的用户需求、目标API名。如果输入完整包含这些信息，则执行下一步；否则，与用户进行沟通。

2. 使用提取的信息使用`SelectAPIParam`，获得目标API的所有需要填写的参数字段与相关信息。

3. `SelectAPIParam`会返回一个JSON列表，你需要**原封不动**地输出该列表，**你不得对列表进行任何内容更改或缺漏**。"""

_tools = [SelectAPIParam]

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

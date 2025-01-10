from agency_swarm.agents import Agent
from agents.basic_agents.api_agents.tools.FillParamTable import FillParamTable

_name = "Array Filler"

_description = "Array Filler 根据用户需求填写API请求中一个参数列表的值。"

_instructions = """你的任务是严格执行下列步骤：

1. 从输入中提取自然语言的用户需求、目标API名、参数名与其信息（可能包括参数描述、数据类型、是否必要等）。

2. 根据用户需求和参数信息，谨慎而专业地判断该参数的类型属于下列哪一种情况，执行相应步骤：

2.1. **用户需求可以确定不需要，或者没有明确提到相关信息**：直接输出空列表`[]`。

2.2. 该参数**用户需求中需要**，且类型为"Array of strings"等简单类型的Array：从用户需求判断该参数列表中有几个成员，**逐一**为每个成员提取对应的用户子需求，对每个成员**调用函数**`SendMessage()`，向`Param Filler`发送信息，并获得函数的返回值。

2.3. 该参数**用户需求中需要**，且类型为"Array of objects"，且描述中明确指出参见表号：从用户需求判断该参数列表中有几个成员，**逐一**为每个成员提取对应的用户子需求，对每个成员**调用函数**`FillParamTable()`，并获得函数的返回值。**必须调用函数，不要只返回参数值！！！**

3. **在所有函数调用完成后**，将所有返回值合并在一个JSON列表`[]`中，并输出该列表。**即使只有一个返回值，也包在列表中输出。**"""

_tools = [FillParamTable]

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

from agency_swarm.agents import Agent
from agents.basic_agents.api_agents.tools.SelectParamTable import SelectParamTable

_name = "Array Selector"

_description = "Array Selector 根据自然语言需求判断是否需要在API调用时提供某个参数列表。"

_instructions = """你的任务是严格执行下列步骤：

1. 从输入中提取自然语言的用户需求、目标API名、参数名与其信息（可能包括参数描述、数据类型等）。

2. 根据用户需求和参数信息，谨慎而专业地判断该参数属于下列哪一种情况，执行相应步骤：

2.1. **用户需求可以确定不需要，或者没有明确提到相关信息**：直接输出"不需要该参数"。

2.2. 该参数**用户需求中需要**，且类型为"Array of strings"等简单类型的Array：直接输出"需要该参数"。

2.3. 该参数**用户需求中需要**，且类型为"Array of objects"：从用户需求判断该参数列表中有几个成员，逐一为每个成员提取对应的用户子需求，对每个成员**调用函数**`SelectParamTable()`，并获得函数的返回值。**必须调用函数，不要只返回参数值！！！**

**在所有函数调用完成后**，将所有返回值合并在一个JSON列表`[]`中，并输出该列表。**重复的项只输出一遍。**
"""

_tools = [SelectParamTable]

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

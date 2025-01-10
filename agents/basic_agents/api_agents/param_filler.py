from agency_swarm.agents import Agent
from agents.base_agents.tools.FillParamTable import FillParamTable

_name = "Param Filler"

_description = "Param Filler 根据用户需求填写API请求中一项参数的值。"

_instructions = """你的任务是严格执行下列步骤，根据用户需求填写API请求中一项参数的值，**不要输出思考过程**：

1. 从输入中提取自然语言的用户需求、目标API名、参数名与参数信息（可能包括参数描述、数据类型、是否必选等）。

2. 根据用户需求和参数信息，谨慎而专业地判断该参数的值属于下列哪一种情况，执行相应步骤：

2.1. **用户需求可以确定不需要，或没有明确提到相关信息**：直接输出"不需要该参数"。**注意：必选参数不能不需要。**

2.2. 该参数**用户需求中需要**，且用户需求中提供了该参数的值：直接**按照数据类型**输出该值。

2.3. 该参数**用户需求中需要**，且属于Array类型（包括Array of Objects）：**调用函数**`SendMessage()`，向`Array Filler`**以JSON格式**发送如下信息：

```json
{
   "user_requirement": "<自然语言的用户需求>",
   "api_name": "<目标API名>",
   "parameter": "<参数名>",
   "description": "<参数描述>",
   "mandatory": "<是否必要（如果有）>",
   "type": "<参数类型（如果有）>"
}
```

最后，**精确**输出对方的回复，**不得输出任何其它内容**。

2.4. 该参数**用户需求中需要**，且属于Object类型，有若干子参数：需参考另一张参数表。**调用函数**`FillParamTable()`，并**精确**输出该函数的返回值，**不得输出任何其它内容**。"""

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

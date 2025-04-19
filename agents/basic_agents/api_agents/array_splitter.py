from agency_swarm.agents import Agent

_name = "Array Spiltter"

_description = "Array Spiltter 根据用户需求判断需要几个实体"

_input_format = """
{
   "user_requirement": <用户需求>,
   "parameter": <你需要判断的参数名>,
   "description": <参数描述>,
}
"""

_instructions = f"""你的任务是每当接收到输入时，都需要**从头**严格执行下列步骤：

你将接受到如下json格式的输入：
{_input_format}

其中，"user_requirement"字段填入了用户需求，"parameter"和"description"字段填入了你需要判断的参数名称和描述

你需要根据**用户需求**和**参数信息**，一步步思考，谨慎而专业地判断该参数应该包含几个实体成员(如果无法判断，默认为1个成员)，并依次为每个成员提取对应的用户子需求

举例：如果参数类型为"Array of NetworkSubnet objects"，"user_requirement"为"查询子网ID为vpc_id1和vpc_id2的子网详细信息"，你得到的用户子需求为"查询子网ID为vpc_id1的子网详细信息"和"查询子网ID为vpc_id2的子网详细信息"。

你应该返回一个列表，其中包含所有实体成员的用户子需求，如上面例子中，你应该返回以下内容:

```json
["查询子网ID为vpc_id1的子网详细信息", "查询子网ID为vpc_id2的子网详细信息"]
```
"""

_tools = []

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

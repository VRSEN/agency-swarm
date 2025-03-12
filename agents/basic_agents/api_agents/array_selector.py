from agency_swarm.agents import Agent
from agents.basic_agents.api_agents.tools.SelectParamTable import SelectParamTable

_name = "Array Selector"

_description = "Array Selector 根据自然语言需求判断是否需要在API调用时提供某个参数列表。"

_input_format = """
{
   "user_requirement": <用户需求>,
   "api_name": <调用的API名称>,
   "parameter": <你需要判断的参数名>,
   "description": <参数描述>,
   "parents_description": <前置参数描述>
   "type": "<数据类型>",
   "mandatory": <该参数是否必选>
}
"""

_instructions = f"""你的任务是每当接收到输入时，都需要**从头**严格执行下列步骤：

你将接受到如下json格式的输入：
{_input_format}

其中，"user_requirement"字段填入了用户需求，"api_name"字段填入了调用的api名称（你不能对api_name进行任何修改），"parameter"和"description"字段填入了你需要判断的参数名称和描述，"parents_description"字段填入了该参数的前置参数的描述（如果为空说明该参数没有前置参数），"type"字段填入该参数的类型，"mandatory"字段为1说明该参数必选

你需要根据**用户需求**和**参数信息**，一步步思考，谨慎而专业地判断该参数属于下列哪一种情况，执行相应步骤：

1. 如果该参数类型为"Array of strings"等简单类型的Array，你需要直接输出"需要该参数"；

2. 如果参数类型为"Array of objects"，你需要从用户需求中判断该参数列表中有几个成员，并依次为每个成员提取对应的用户子需求；

举例：如果参数类型为"Array of NetworkSubnet objects"，"user_requirement"为"查询子网ID为vpc_id1和vpc_id2的子网详细信息"，你得到的用户子需求为"查询子网ID为vpc_id1的子网详细信息"和"查询子网ID为vpc_id2的子网详细信息"。

然后你需要对每个成员使用`SelectParamTable`进一步处理。所有成员都经过以上处理后，你需要将所有成员`SelectParamTable`的返回结果合并到一个JSON列表中，并输出该列表。
"""

"""
如果""
1. 如果**用户需求可以确定不需要，或者没有明确提到相关信息**，你需要直接输出"不需要该参数"。

2. 该参数**用户需求中需要**，且类型为"Array of strings"等简单类型的Array：直接输出"需要该参数"。

3. 该参数**用户需求中需要**，且类型为"Array of objects"：从用户需求判断该参数列表中有几个成员，逐一为每个成员提取对应的用户子需求，对每个成员**调用函数**`SelectParamTable`，并获得函数的返回值。**必须调用函数，不要只返回参数值！！！**
并且，你需要**在所有函数调用完成后**，将所有返回值合并在一个JSON列表`[]`中，并输出该列表。**重复的项只输出一遍。**
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

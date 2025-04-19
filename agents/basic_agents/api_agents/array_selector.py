from agency_swarm.agents import Agent
from agents.basic_agents.api_agents.tools.SplitArray import SplitArray

_name = "Array Selector"

_description = "Array Selector 根据自然语言需求判断是否需要在API调用时提供某个参数列表。"

_input_format = """
{
   "user_requirement": <用户需求>,
   "api_name": <调用的API名称>,
   "parameter": <你需要判断的参数名>,
   "id": <你需要判断的参数编号>,
   "description": <参数描述>,
   "parents_description": <前置参数描述>
   "type": "<数据类型>",
   "mandatory": <该参数是否必选>
}
"""

_instructions = f"""你的任务是每当接收到输入时，都需要**从头**严格执行下列步骤：

你将接受到如下json格式的输入：
{_input_format}

其中，"user_requirement"字段填入了用户需求，"api_name"字段填入了调用的api名称（你不能对api_name进行任何修改），"parameter","id"和"description"字段填入了你需要判断的参数名称、编号和描述，"parents_description"字段填入了该参数的前置参数的描述（如果为空说明该参数没有前置参数），"type"字段填入该参数的类型，"mandatory"字段为1说明该参数必选

你需要根据**用户需求**和**参数信息**，一步步思考，谨慎而专业地判断该参数属于下列哪一种情况，执行相应步骤：

1. 如果该参数类型为"Array of strings"等简单类型的Array，你需要直接输出"需要该参数"；

2. 如果参数类型为"Array of objects"，你需要使用`SplitArray`处理该参数，SplitArray会返回一个JSON列表，你需要**原封不动**地输出该JSON列表

# 注意，你不得对返回结果有任何修改或遗漏信息
"""

_tools = [SplitArray]

_files_folder = ""

def create_agent(*,
                 name=_name,
                 description=_description,
                 instructions=_instructions,
                 tools=_tools,
                 files_folder=_files_folder):
    return Agent(name=name,
                 tools=tools,
                 # response_format=[],
                 description=description,
                 instructions=instructions,
                 files_folder=files_folder,
                 temperature=0.5,
                 max_prompt_tokens=25000,
                 )

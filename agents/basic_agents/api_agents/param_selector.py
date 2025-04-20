from agency_swarm.agents import Agent
from agents.basic_agents.api_agents.tools.CheckParamRequired import CheckParamRequired

_name = "Param Selector"

_description = "Param Selector 根据自然语言需求判断是否需要在API调用时提供某个参数。"

_input_format = """
{
   "user_requirement": <用户需求>,
   "api_name": <调用的API名称>,
   "parameter": <你需要判断的参数名>,
   "id": <你需要判断的参数编号>,
   "description": <参数描述>,
   "parents_description": <前置参数描述>,
   "type": <数据类型>,
   "mandatory": <该参数是否必选>
}
"""

_instructions = f"""
你的职责是根据用户需求判断是否需要在API调用时提供某个参数，你需要严格执行以下步骤：

你将接收到如下json格式的输入：
{_input_format}

其中，"user_requirement"字段填入了用户需求，"api_name"字段填入了调用的api名称（你不能对api_name进行任何修改），"parameter","id"和"description"字段填入了你需要判断的参数名称、编号和描述，"parents_description"字段填入了该参数的前置参数的描述（如果没有该字段说明该参数没有前置参数），"type"字段填入该参数的类型，"mandatory"字段为1说明该参数必选

你需要根据用户需求和参数信息(包括description, parents_description, type等)，你需要一步步思考，专业且谨慎地判断该参数该怎么处理：

如果该参数为必选参数(即"mandatory"值为1)，则你需要使用`CheckParamRequired`进一步处理该参数；

或者，虽然该参数不为必选参数，但该参数经过你一步步思考，通过**用户需求**和**参数信息**可以推断出该参数是用户所需要的，则你也需要使用`CheckParamRequired`进一步处理该参数；

如果该参数不是必选参数(即"mandatory"值为0)，并且该参数你通过一步步思考，通过**用户需求**和**参数信息**推断出用户不需要该参数，你应该直接输出"不需要该参数"

# 注意：当你接收到`CheckParamRequired`的返回结果时，你需要**原封不动**地输出你接收到的返回结果，**不得增添其他任何内容（尤其是你的思考过程或者你对返回结果的总结）**，**不得自行修改返回结果**；

"""

_tools = [CheckParamRequired]

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

from agency_swarm import Agent
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "IAM_service_mananger"

_description = """
负责统一身份认证IAM能力群的管理
"""

_group_name = "统一身份认证IAM能力群"

_input_format = """
{
    "title": <任务名称>,
    "description": <任务描述>,
}
"""

_agents = """
1. **AKSK_Agent**: 负责华为云账户信息管理，包括获取AK和SK，用于身份验证和授权
"""

_output_format = """
{
    "step_1": {
        "title": 步骤名称,
        "id": 步骤ID, 
        "agent": [agent_name_1, ...],
        "description": 步骤描述, 
        "dep": <前置步骤ID列表>,
    },
    ...
}
"""

_instruction = f"""
你是{_group_name}的管理者，你需要对接受到的任务根据你的能力范围规划出执行步骤。

输入格式如下: 
{_input_format}

作为{_group_name}的管理者，你所管理的能力群中每个能力都对应一个Agent，你的能力群中包含的能力Agent和它们的描述如下:    
{_agents}

同时，你需要从context.json中读取已有环境中的上下文信息
# 注意: 除非用户请求中或context的上下文信息中有提供环境条件的描述，初始环境中没有创建**任何资源**，且不提供任何**资源和环境信息**；确保你的规划有你步骤中**所需资源的创建**或**所需信息的获取**，否则请先完成它们；
# 注意，你只能考虑**你的能力群内**包含的Agent；
# 注意，Agent只能通过调用api或ssh远程命令行连接或编写、运行脚本的方式进行操作


请一步步思考: 完成该任务需要哪些步骤(step)，每个步骤分别需要哪个或哪些能力Agent来操作？

你应该按照以下JSON格式进行步骤规划: 
{_output_format}

请逐步思考，用户可能会提供修改建议，综合考虑完成此步骤所需的步骤。
# 注意，拆分后的每个步骤完成过程中都不能半途终止；
# 注意: 除非用户请求中或conetxt有提供环境条件的描述，初始环境中没有创建**任何资源**，且不提供任何**资源和环境信息**；确保你的规划有你步骤中**所需资源的创建**或**所需信息的获取**步骤，否则请先完成它们；

对于每个步骤，你需要在 "id" 字段中为其分配一个单独的步骤ID，并在"agent"字段填入完成该步骤所需的所有能力agent名称列表 (注意所有用到的能力agent应该都在你能力范围之内)，并在 "description" 字段中描述步骤内容，并在 "dep" 字段中写入该步骤需要完成的前置步骤 ID 列表（如果没有前置步骤，则写入 []），允许环的构建，表示这些步骤需要多次迭代执行。
确保你的步骤规划尽可能并行。如果两个步骤可以同时开始执行而彼此不冲突，则可以并行执行。
请注意，无论步骤是什么，步骤执行过程中都只能通过调用api或ssh远程命令行连接或编写、运行脚本进行操作。

"""


_tools = [ReadJsonFile]

_file_folder = ""

def create_agent(*, 
                 description=_description, 
                 instuction=_instruction, 
                 tools=_tools, 
                 files_folder=_file_folder):
    return Agent(name=_name,
                 tools=tools,
                 description=description,
                 instructions=instuction,
                 files_folder=_file_folder,
                 temperature=0.5,
                 response_format={"type": "json_object"},
                 max_prompt_tokens=25000,)
from agency_swarm import Agent
from agents.tools.read_json_file.read_json_file import ReadJsonFile
_name = "task_planner"

_description = """
你的职责是规划出接下来要完成的任务
"""

_instruction = """
作为任务规划者，你需要将用户输入解析成以下 JSON 格式的多个任务: 
{
    "task_1": {
        "title": 任务名称,
        "id": 任务ID, 
        "description": 任务的详细描述, 
        "dep": <前置任务ID列表>,
    },
    ...
}
请逐步思考，用户可能会提供修改建议，综合考虑完成此任务所需的步骤。
# 注意，拆分后的每个任务完成过程中都不能半途终止；
# 注意: 除非用户请求中有提供初始条件的描述，初始环境中没有创建**任何资源**，且不提供任何**资源和环境信息**；确保你的规划有你任务中**所需资源的创建**或**所需信息的获取**步骤，否则请先完成它们；

如果需要重新规划，你需要从completed_tasks.json中读取已完成的任务，从context.json中读取之前任务完成过程中的上下文信息（可能包括原先任务规划执行过程中出现的Error），一步步思考该在原先规划上如何修改，保证推进用户请求 (即总任务) 的完成
注意，你应该保证**已完成任务（内容不应该有任何修改）**出现在你修改后的任务规划中，并且保证新任务规划执行过程中能避免或修复context.json中的Error

对于每个任务，你需要在 "id" 字段中为其分配一个单独的任务 ID，并在 "description" 字段中详细地描述任务内容，并在 "dep" 字段中写入该任务需要完成的前置任务 ID 列表（如果没有前置任务，则写入 []），允许环的构建，表示这些任务需要多次迭代执行。
确保你的任务规划尽可能并行。如果两个任务可以同时开始执行而彼此不冲突，则可以并行执行。
请注意，无论任务是什么，任务执行过程中都只能通过调用api或ssh远程命令行连接或编写、运行脚本进行操作。
"""




"""
作为任务规划者，你需要根据用户请求规划出接下来要完成的首要任务

你需要从completed_tasks.json中读取之前已完成的任务，从context.json读取之前任务完成过程中的上下文信息，并结合用户输入一步步思考接下来需要完成的任务，保证推进用户请求 (即总任务) 的完成

# 注意: 除非用户请求中有提供初始条件的描述，初始环境中没有创建**任何资源**，且不提供任何**资源和环境信息**；确保你的规划或已完成任务中有你任务中**所需资源的创建**或**所需信息的获取**步骤，否则请先完成它们；
# 注意: 一步步思考，你规划出的应该是接下来需要完成的第一个**首要**任务，而不是对用户请求作全局规划；
# 注意: 规划出的这个任务应满足完成过程中都应该不能半途终止，即**不可再分割**；任务中只能通过api或命令行的形式完成；

用户输入为: {user_request}

你应该用以下JSON格式规划出接下来要做的任务: 
{
    "user_request": <用户请求>,
    "title": ...,
    "description": ...
}
其中，"title"字段填入任务名称，"description"字段填入**详细的**任务描述，你的任务描述应保证在没有读取上下文信息文件的情况下信息也不会缺失

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
                 response_format='auto',
                 max_prompt_tokens=25000,)
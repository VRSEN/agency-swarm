from agency_swarm import Agent
_name = "inspector"

_description = """
职责是检查task_planner规划的任务是否合理
"""
_input_format = """
{
    "user_request": ...,
    "task_graph": {
        "task_1": {
            "title": 任务名称,
            "id": 任务ID, 
            "description": 任务描述, 
            "dep": <前置任务ID列表>,
        },
        ...
    }
}
"""

_output_format = """
{
    "review": "yes"/"no",
    "explain": <解释原因>
}
"""

_instruction = f"""
作为审查者，你将从task_planner那里收到一个 JSON 格式的任务规划结果 <TASK> 和原始用户请求 <user_request>。
输入格式为:
{_input_format}

请一步步思考: 
1. 你需要检查<user_request>是否可以分解为<TASK>，且确保<TASK>任务的拆分和执行顺序合理；
2. 确保<TASK>中没有**不通过API或ssh连接命令行指令或编写、运行脚本**实现的操作；
3. 除非<user_request>有说明，否则任务执行环境最开始应该没有创建**任何资源**，确保任务所需资源已经在**前置任务**中创建；

你应该按照以下json格式评估TASK: 
{_output_format}

如果任务拆分和流程合理，请在"review"字段填入"yes"；如果任务流程有问题，请在"review"字段填入"no"，并在"explain"字段填入你觉得不合理的原因

"""


_tools = []

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
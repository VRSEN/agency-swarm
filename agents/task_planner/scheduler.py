from agency_swarm import Agent
from agents.tools.read_json_file.read_json_file import ReadJsonFile
_name = "scheduler"

_description = """
职责是调度任务
"""

_instruction = """
作为调度者，你将接收到任务流程和初始用户请求，输入格式如下:  
你将从task_planner那里收到一个 JSON 格式的任务规划结果 <TASK> 和原始用户请求 <user_request>。
输入格式为:
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

你需要从completed_tasks.json中读取已完成的任务，从context.json中读取之前任务完成过程中的上下文信息，并结合用户输入一步步思考接下来需要完成的任务，保证推进用户请求 (即总任务) 的完成

你需要根据已完成任务和上下文信息选出下一步可执行的所有任务，确保它们可以**并行执行**；如果两个任务可以同时开始执行而彼此不冲突，则可以并行执行。

你的最终调度结果应该为: 
{
    "completed_tasks": ...,
    "context": ...,
    "next_tasks": [id_1, ...],
    "reason": ...
}

你需要在"reason"字段填入你选出这些任务的原因
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
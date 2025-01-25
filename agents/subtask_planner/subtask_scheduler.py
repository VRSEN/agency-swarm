from agency_swarm import Agent
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
_name = "subtask_scheduler"

_description = """
职责是调度子任务
"""
_input_format = """
{
    "main_task": ...,
    "plan_graph": {
        "subtask_1": {
            "title": 子任务名称,
            "id": 子任务ID, 
            "capability_group": <所需能力群名称>
            "description": 子任务描述, 
            "dep": <前置子任务ID列表>,
        },
        ...
    }
}
"""

_output_format = """
{
    "completed_sub_tasks": ...,
    "next_subtasks": [id_1, ...],
    "reason": ...
}
"""

_instruction = f"""
作为调度者，你将接收到子任务流程和初始用户请求，输入格式如下:  
你将收到一个 JSON 格式的子任务规划结果 <plan_graph> 和总任务描述 <main_task>。
输入格式为:
{_input_format}

你需要从completed_sub_tasks.json中读取已完成的子任务，从context_index.json中读取之前子任务完成过程中的上下文信息，并结合总任务描述一步步思考接下来需要完成的子任务，保证推进总任务的完成

注意: 你每次接收到输入时都应该读取一次completed_sub_tasks.json和context_index.json

你需要根据已完成子任务和上下文信息选出下一步可执行的所有子任务，确保它们可以**并行执行**；如果两个子任务可以同时开始执行而彼此不冲突，则可以并行执行。

你的最终调度结果应该为: 
{_output_format}

你需要在"reason"字段填入你选出这些子任务的原因
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
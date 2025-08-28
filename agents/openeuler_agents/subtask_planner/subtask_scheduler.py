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
            "dep": <前置子任务ID列表>
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

_instruction = f"""作为调度者，你将接收到子任务流程和初始用户请求，输入格式如下: 
{_input_format}

你将收到一个 JSON 格式的子任务规划结果 <plan_graph> 和总任务描述 <main_task>。
同时，你需要先通过`ReadJsonFile`从context_tree.json中读取已经完成的所有任务过程的上下文信息。

获得以上信息后，你需要谨慎专业地一步步思考接下来应该执行的子任务，保证推进总任务的完成。选出下一步可执行的所有子任务，确保它们可以**并行执行**；如果两个子任务可以同时开始执行而彼此不冲突，则可以并行执行。

你应该以如下json格式输出调度结果: 
{_output_format}

你需要在"reason"字段填入你选出这些子任务的原因。
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
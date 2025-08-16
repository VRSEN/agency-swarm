from agency_swarm import Agent
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
_name = "task_scheduler"

_description = """
职责是调度任务
"""

_input_format = """
{
    "main_task": ...,
    "plan_graph": {
        "task_1": {
            "title": 任务名称,
            "id": 任务ID, 
            "description": 任务描述, 
            "dep": <前置任务ID列表>
        },
        ...
    }
}
"""

_output_format = """
{
    "completed_tasks": ...,
    "next_tasks": [id_1, ...],
    "reason": ...
}
"""

_instruction = f"""作为调度者，你将接收到任务流程和初始用户请求，输入格式如下: 
{_input_format}

你将收到一个 JSON 格式的任务规划结果 <plan_graph> 和总任务描述 <main_task>。
同时，你需要先从context_tree.json中读取已经完成的所有过程的上下文信息。

获得以上信息后，你需要谨慎专业地一步步思考接下来应该执行的任务，保证推进总任务的完成。选出下一步可执行的所有任务，确保它们可以**并行执行**；如果两个任务可以同时开始执行而彼此不冲突，则可以并行执行。

你应该以如下json格式输出调度结果: 
{_output_format}

你需要在"reason"字段填入你选出这些任务的原因。
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
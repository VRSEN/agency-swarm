from agency_swarm import Agent
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
_name = "Huawei_Cloud_API_step_scheduler"

_description = """
职责是调度华为云API处理能力群的step，选出下一步可以执行的step
"""
_input_format = """
{
    "main_task": ...,
    "plan_graph": {
        "step_1": {
            "title": step名称,
            "id": step ID, 
            "agent": [agent_name_1, ...],
            "description": step描述, 
            "dep": <前置step ID列表>,
        },
        ...
    }
}
"""

_output_format = """
{
    "completed_steps": ...,
    "next_steps": [id_1, ...],
    "reason": ...
}
"""

_instruction = f"""
作为调度者，你将接收到step流程和初始用户请求，输入格式如下:  
你将从task_planner那里收到一个 JSON 格式的step规划结果 <plan_graph> 和总任务描述 <main_task>。
输入格式为:
{_input_format}

你需要从completed_steps.json中读取已完成的step，从context.json中读取之前step完成过程中的上下文信息，并结合总任务描述一步步思考接下来需要完成的step，保证推进总任务的完成

你需要根据已完成step和上下文信息选出下一步可执行的所有step，确保它们可以**并行执行**；如果两个step可以同时开始执行而彼此不冲突，则可以并行执行。

你的最终调度结果应该为: 
{_output_format}

你需要在"reason"字段填入你选出这些step的原因
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
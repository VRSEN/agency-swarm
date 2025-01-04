from agency_swarm import Agent
from agents.cap_group_agents.step_scheduler_instruction import step_scheduler_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
_name = "VPC_network_step_scheduler"

_description = """
职责是调度VPC网络管理能力群的step，选出下一步可以执行的step
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

_instruction = step_scheduler_instruction(_input_format, _output_format)

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
from agency_swarm import Agent
from agents.openeuler_agents.os_group import os_planner
from agents.openeuler_agents.rag_optimize_instruction import rag_optimize_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "os_rag_optimizer"

_description = """
负责操作系统能力群的任务细化
"""

_group_name = "操作系统能力群"

_input_format = """
{
    "title": <任务名称>,
    "description": <任务描述>,
    "total_task_graph": <所有任务的规划图>,
    "last_error": <之前执行该任务时的错误信息>
}
"""

_output_format = """
{
    "description": 任务描述,
    "agent": [agent_name_1, ...]
}
"""

_os_agents = os_planner._agents

_instruction = rag_optimize_instruction(
    _group_name, _input_format, _os_agents, _output_format
)

_tools = [ReadJsonFile]

_file_folder = ""


def create_agent(
    *,
    description=_description,
    instuction=_instruction,
    tools=_tools,
    files_folder=_file_folder,
):
    return Agent(
        name=_name,
        tools=tools,
        description=description,
        instructions=instuction,
        files_folder=files_folder,
        temperature=0.5,
        response_format="auto",
        max_prompt_tokens=25000,
    )

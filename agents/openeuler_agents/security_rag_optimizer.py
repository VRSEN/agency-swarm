from agency_swarm import Agent
from agents.openeuler_agents.rag_optimize_instruction import rag_optimize_instruction
from agents.openeuler_agents.security_group import security_planner
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "security_rag_optimizer"

_description = """
负责安全能力群的任务细化
"""

_group_name = "安全能力群"

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

_security_agents = security_planner._agents

_instruction = rag_optimize_instruction(
    _group_name, _input_format, _security_agents, _output_format
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

from agency_swarm import Agent
from agents.k8s_group_agents.planner_instruction import planner_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "pod_manage_planner"

_description = """
负责pod管理能力群的步骤规划
"""

_group_name = "pod管理能力群"

_input_format = """
{
    "total_subtask_graph": <所有子任务的规划图>,
    "title": <任务名称>,
    "description": <任务描述>,
}
"""

_agents = """
1. **pod_manage_agent**: 负责k8s集群的pod管理任务，包括：创建、查询、修改、停止、删除pod。例如，查询状态或配置。
2. **resource_grouping_agent**: 负责k8s集群的pod资源分组任务，包括：1.Label管理。例如，按标签查询，为Pod分配合理的Label；2.Namespace管理。例如，创建、查询、删除Namespace，为Pod分配Namespace。
"""

_output_format = """
{
    "step_1": {
        "title": 步骤名称,
        "id": 步骤ID, 
        "agent": [agent_name_1, ...],
        "description": 步骤描述, 
        "dep": <前置步骤ID列表>,
    },
    ...
}
"""

_instruction = planner_instruction(_group_name, _input_format, _agents, _output_format)


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
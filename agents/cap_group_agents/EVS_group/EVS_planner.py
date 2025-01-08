from agency_swarm import Agent
from agents.cap_group_agents.planner_instruction import planner_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "EVS_planner"

_description = """
负责云硬盘EVS管理能力群的步骤规划
"""

_group_name = "云硬盘EVS管理能力群"

_input_format = """
{
    "title": <任务名称>,
    "description": <任务描述>,
}
"""

_agents = """
1.**CloudDiskManager Agent**: 专门负责处理华为云的云硬盘管理相关操作，包括创建、删除、查询、更新、扩容、配置QoS云硬盘。
2.**CloudDiskSnapshotManager Agent**: 专门负责处理华为云的云硬盘快照管理相关操作，包括创建、删除、更新、查询云硬盘快照。
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